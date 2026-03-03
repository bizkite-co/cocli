import typer
import asyncio
import logging
import toml
import json
import csv
import httpx
from typing import Optional, List, Dict, Any, cast, Annotated
from pathlib import Path
from rich.console import Console
from playwright.async_api import async_playwright
import yaml

from cocli.core.paths import paths
from cocli.core.config import get_companies_dir, get_campaign_dir, get_campaign, get_enrichment_service_url

from cocli.core.scrape_index import ScrapeIndex
from cocli.core.text_utils import slugify
from cocli.core.location_prospects_index import LocationProspectsIndex
from cocli.core.queue.factory import get_queue_manager
from cocli.planning.generate_grid import get_campaign_grid_tiles
from cocli.models.campaigns.queues.gm_list import ScrapeTask
from cocli.models.companies.company import Company
from cocli.models.companies.website import Website
from cocli.scrapers.google_maps import scrape_google_maps
from cocli.scrapers.google_maps_details import scrape_google_maps_details
from cocli.compilers.website_compiler import WebsiteCompiler
from cocli.core.enrichment import enrich_company_website

logger = logging.getLogger(__name__)
console = Console()
app = typer.Typer(no_args_is_help=True)

async def pipeline(
    locations: list[str],
    search_phrases: list[str],
    goal_emails: int,
    headed: bool,
    devtools: bool,
    campaign_name: str,
    existing_companies_map: Dict[str, str],
    overlap_threshold_percent: float,
    zoom_out_button_selector: str,
    panning_distance_miles: int,
    initial_zoom_out_level: int,
    omit_zoom_feature: bool,
    force: bool,
    ttl_days: int,
    debug: bool,
    console: Console,
    browser_width: int,
    browser_height: int,
    location_prospects_index: LocationProspectsIndex,
    target_locations: Optional[List[Dict[str, Any]]] = None,
    aws_profile_name: Optional[str] = None,
    campaign_company_slug: Optional[str] = None,
    use_cloud_queue: bool = False,
    max_proximity_miles: float = 0.0,
    navigation_timeout_ms: Optional[int] = None,
    proxy_url: Optional[str] = None,
    grid_tiles: Optional[List[Dict[str, Any]]] = None,
) -> None:
    
    queue_manager = get_queue_manager(f"{campaign_name}_enrichment", use_cloud=use_cloud_queue)
    stop_event = asyncio.Event()
    emails_found_count = 0
    
    launch_proxy = {"server": proxy_url} if proxy_url else None

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not headed,
            devtools=devtools,
            proxy=cast(Any, launch_proxy),
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        
        async def consumer_task() -> None: 
            nonlocal emails_found_count
            enrichment_url = get_enrichment_service_url()
            use_cloud_enrichment = enrichment_url != "http://localhost:8000"
            consumer_context = await browser.new_context() if not use_cloud_enrichment else None
            compiler = WebsiteCompiler()
            
            while not stop_event.is_set():
                messages = await asyncio.to_thread(queue_manager.poll, batch_size=1)
                if not messages:
                    await asyncio.sleep(1)
                    continue
                
                for msg in messages:
                    if stop_event.is_set():
                        break
                    console.print(f"[dim]Processing: {msg.domain}[/dim]")
                    website_data = None
                    
                    if use_cloud_enrichment:
                        async with httpx.AsyncClient() as client:
                            try:
                                response = await client.post(f"{enrichment_url}/enrich", json={
                                    "domain": msg.domain, "force": msg.force_refresh, "ttl_days": msg.ttl_days,
                                    "campaign_name": msg.campaign_name, "company_slug": msg.company_slug,
                                    "navigation_timeout_ms": navigation_timeout_ms
                                }, timeout=120.0)
                                response.raise_for_status()
                                website_data = Website(**response.json())
                            except Exception as e:
                                logger.error(f"Enrichment failed for {msg.domain}: {e}")
                                queue_manager.nack(msg)
                                continue
                    else:
                        dummy_company = Company(name=msg.domain, domain=msg.domain, slug=msg.company_slug)
                        try:
                            if consumer_context:
                                website_data = await enrich_company_website(browser=consumer_context, company=dummy_company, force=msg.force_refresh, ttl_days=msg.ttl_days)
                            else:
                                logger.error("No browser context available for consumer task")
                                queue_manager.nack(msg)
                                continue
                        except Exception:
                            queue_manager.nack(msg)
                            continue

                    if website_data:
                        company_dir = get_companies_dir() / msg.company_slug
                        company_dir.mkdir(parents=True, exist_ok=True)
                        enrichment_dir = company_dir / "enrichments"
                        enrichment_dir.mkdir(parents=True, exist_ok=True)
                        with open(enrichment_dir / "website.md", "w") as f:
                            f.write("---\n")
                            yaml.dump(website_data.model_dump(exclude_none=True), f)
                            f.write("---\n")
                        compiler.compile(company_dir)
                        if website_data.email:
                            emails_found_count += 1
                        if emails_found_count >= goal_emails:
                            stop_event.set()
                        queue_manager.ack(msg)
            
            compiler.save_audit_report()
        async def producer_task(existing_companies_map: Dict[str, str]) -> None: 
            # Discovery-only in producer task
            from ...models.campaigns.queues.base import QueueMessage
            
            enrichment_queue = get_queue_manager(
                f"{campaign_name}_enrichment", 
                use_cloud=use_cloud_queue
            )

            prospect_generator = scrape_google_maps(
                browser=browser, location_param={"latitude": "0", "longitude": "0"},
                search_strings=search_phrases, campaign_name=campaign_name, grid_tiles=grid_tiles,
                force_refresh=force, ttl_days=ttl_days, debug=debug, max_proximity_miles=max_proximity_miles,
                overlap_threshold_percent=overlap_threshold_percent
            )
            async for list_item in prospect_generator:
                if stop_event.is_set():
                    break
                
                # In-process Detailing for achieve-goal
                page = await browser.new_page()
                try:
                    detailed_data = await scrape_google_maps_details(
                        page=page,
                        place_id=list_item.place_id,
                        campaign_name=campaign_name,
                        name=list_item.name,
                        company_slug=list_item.company_slug,
                        debug=debug
                    )
                    
                    if detailed_data and detailed_data.domain:
                        msg = QueueMessage(
                            domain=detailed_data.domain,
                            company_slug=detailed_data.company_slug or list_item.company_slug,
                            campaign_name=campaign_name,
                            force_refresh=force,
                            ack_token=None
                        )
                        enrichment_queue.push(msg)
                finally:
                    await page.close()
                
                await asyncio.sleep(0.01)

        try:
            async with asyncio.timeout(300): # 5-minute watchdog
                await asyncio.gather(producer_task(existing_companies_map), consumer_task())
        except asyncio.TimeoutError:
            console.print("[yellow]Pipeline timed out after 5 minutes.[/yellow]")
        finally:
            stop_event.set()

@app.command(name="queue-scrapes")
def queue_scrapes(
    campaign_name: Optional[str] = typer.Argument(None),
    include_legacy: bool = typer.Option(False, "--include-legacy"),
    force: bool = typer.Option(False, "--force"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report task count without enqueuing."),
) -> None:
    if campaign_name is None:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[red]Campaign directory not found for {campaign_name}[/red]")
        raise typer.Exit(1)

    config_path = campaign_dir / "config.toml"
    with open(config_path, "r") as f:
        config = toml.load(f)
    search_phrases = config.get("prospecting", {}).get("queries", [])
    
    grid_tiles = get_campaign_grid_tiles(campaign_name)
    tasks_to_queue = []
    total_combinations = 0
    
    if grid_tiles:
        scrape_index = ScrapeIndex()
        
        total_combinations = len(grid_tiles) * len(search_phrases)
        
        for tile in grid_tiles:
            lat = tile.get("center_lat") or tile.get("center", {}).get("lat")
            lon = tile.get("center_lon") or tile.get("center", {}).get("lon")
            tile_id = tile.get("id")
            if lat and lon and tile_id:
                # bounds for 0.1 degree tile
                bounds = {"lat_min": float(lat)-0.05, "lat_max": float(lat)+0.05, "lon_min": float(lon)-0.05, "lon_max": float(lon)+0.05}
                for phrase in search_phrases:
                    if not force:
                        # 1. Direct Tile Check (Fastest)
                        match_area = scrape_index.is_tile_scraped(phrase, tile_id, ttl_days=30)
                        if match_area:
                            continue
                            
                        # 2. Overlap Check (Legacy and Robustness)
                        match = scrape_index.is_area_scraped(phrase, bounds, overlap_threshold_percent=90.0)
                        if match and (include_legacy or match[0].tile_id):
                            continue

                    tasks_to_queue.append(ScrapeTask(
                        latitude=float(lat), 
                        longitude=float(lon), 
                        zoom=13, 
                        search_phrase=phrase, 
                        campaign_name=campaign_name, 
                        tile_id=tile.get("id"),
                        ack_token=None
                    ))
    
    if dry_run:
        covered = total_combinations - len(tasks_to_queue)
        covered_pct = (covered / total_combinations * 100) if total_combinations > 0 else 0
        console.print(f"[bold cyan]DRY RUN Summary for {campaign_name}:[/bold cyan]")
        console.print(f"  Total Tile/Phrase Combinations: {total_combinations}")
        console.print(f"  Already Covered:                {covered} ({covered_pct:.1f}%)")
        console.print(f"  [bold yellow]Remaining to Scrape:            {len(tasks_to_queue)}[/bold yellow]")
        return

    if tasks_to_queue:
        # Silence verbose libraries
        logging.getLogger("botocore").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("cocli").setLevel(logging.INFO)
        
        queue_manager = get_queue_manager("scrape_tasks", use_cloud=True, queue_type="scrape")
        
        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            task_id = progress.add_task(f"[cyan]Pushing {len(tasks_to_queue)} tasks...[/cyan]", total=len(tasks_to_queue))
            
            for task in tasks_to_queue:
                queue_manager.push(task)
                progress.advance(task_id)
                
        console.print(f"[bold green]Successfully queued {len(tasks_to_queue)} scrape tasks.[/bold green]")
    else:
        console.print("[yellow]No tasks to queue (all areas covered or no targets found).[/yellow]")

@app.command(name="queue-batch")
def queue_batch(
    campaign_name: Optional[str] = typer.Argument(None),
    limit: int = typer.Option(100, "--limit", help="Number of tasks to enqueue."),
    force: bool = typer.Option(False, "--force"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show tasks without enqueuing."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save tasks to a JSON file instead of enqueuing."),
    no_limit: bool = typer.Option(False, "--no-limit", help="Ignore the limit and process all unscraped areas."),
) -> None:
    """
    Enqueues or exports a batch of scrape tasks for the campaign.
    """
    if campaign_name is None:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[red]Campaign directory not found for {campaign_name}[/red]")
        raise typer.Exit(1)

    config_path = campaign_dir / "config.toml"
    with open(config_path, "r") as f:
        config = toml.load(f)
    search_phrases = config.get("prospecting", {}).get("queries", [])
    
    grid_tiles = get_campaign_grid_tiles(campaign_name)
    tasks_to_queue = []
    
    if grid_tiles:
        scrape_index = ScrapeIndex()
        
        for tile in grid_tiles:
            lat = tile.get("center_lat") or tile.get("center", {}).get("lat")
            lon = tile.get("center_lon") or tile.get("center", {}).get("lon")
            tile_id = tile.get("id")
            if lat and lon and tile_id:
                bounds = {"lat_min": float(lat)-0.05, "lat_max": float(lat)+0.05, "lon_min": float(lon)-0.05, "lon_max": float(lon)+0.05}
                for phrase in search_phrases:
                    if not force:
                        if scrape_index.is_tile_scraped(phrase, tile_id, ttl_days=30):
                            continue
                        if scrape_index.is_area_scraped(phrase, bounds, overlap_threshold_percent=90.0):
                            continue

                    tasks_to_queue.append({
                        "latitude": float(lat), 
                        "longitude": float(lon), 
                        "zoom": 13, 
                        "search_phrase": phrase, 
                        "campaign_name": campaign_name, 
                        "tile_id": tile.get("id"),
                        "ack_token": None
                    })
                    
                    if not no_limit and len(tasks_to_queue) >= limit:
                        break
            if not no_limit and len(tasks_to_queue) >= limit:
                break

    if tasks_to_queue:
        if output:
            with open(output, "w") as f:
                json.dump(tasks_to_queue, f, indent=2)
            console.print(f"[bold green]Successfully exported {len(tasks_to_queue)} tasks to {output}[/bold green]")
            return

        if dry_run:
            console.print(f"[bold blue]Dry Run: Would have queued {len(tasks_to_queue)} tasks:[/bold blue]")
            for t_dict in tasks_to_queue:
                console.print(f" - {t_dict['search_phrase']} @ {t_dict['latitude']}, {t_dict['longitude']} (Tile: {t_dict['tile_id']})")
            return

        queue_manager = get_queue_manager("scrape_tasks", use_cloud=True, queue_type="scrape")
        for t_dict in tasks_to_queue:
            from cocli.models.campaigns.queues.gm_list import ScrapeTask
            queue_manager.push(ScrapeTask(**t_dict))
        console.print(f"[bold green]Successfully queued {len(tasks_to_queue)} tasks.[/bold green]")
    else:
        console.print("[yellow]No tasks to queue.[/yellow]")

@app.command(name="prepare-mission")
def prepare_mission(
    campaign_name: Annotated[Optional[str], typer.Argument(help="The name of the campaign.")] = None,
    ttl_days: int = typer.Option(30, "--ttl-days", help="Tiles scraped longer than this many days ago are considered stale and added to the frontier."),
    debug: bool = typer.Option(False, "--debug", help="Enable diagnostic logging and generate scraped manifest."),
) -> None:
    """
    Generates a deterministic master task list (mission.usv) and calculates the unscraped frontier.
    """
    if campaign_name is None:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[red]Campaign directory not found for {campaign_name}[/red]")
        raise typer.Exit(1)

    # 1. Load Config
    with open(campaign_dir / "config.toml", "r") as f:
        config = toml.load(f)
    
    prospecting_config = config.get("prospecting", {})
    proximity_miles = float(prospecting_config.get("proximity", 10.0))
    search_phrases = prospecting_config.get("queries", [])
    target_locations_csv = prospecting_config.get("target-locations-csv")

    # 2. Load Target Locations
    target_locations: List[Dict[str, Any]] = []
    if target_locations_csv:
        # Search in campaign root OR resources/
        path = campaign_dir / target_locations_csv
        if not path.exists():
            path = campaign_dir / "resources" / target_locations_csv
            
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                rows: List[Dict[str, Any]] = []
                if path.suffix == ".usv":
                    from ...utils.usv_utils import USVDictReader
                    u_reader = USVDictReader(f)
                    rows = list(u_reader)
                else:
                    c_reader = csv.DictReader(f)
                    rows = list(c_reader)
                    
                for row in rows:
                    lat, lon = row.get("lat"), row.get("lon")
                    if lat and lon:
                        target_locations.append({
                            "name": row.get("name") or row.get("city"),
                            "lat": float(lat),
                            "lon": float(lon)
                        })

    # 3. Generate Grid
    console.print(f"[bold]Generating grid for {len(target_locations)} locations (Radius: {proximity_miles} mi)...[/bold]")
    unique_tiles = get_campaign_grid_tiles(campaign_name, target_locations=target_locations)

    # 4. Build Deterministic Task List
    from ...core.geo_types import LatScale6, LonScale6
    tasks = []
    for tile in unique_tiles:
        lat = tile.get("center_lat") or tile.get("center", {}).get("lat")
        lon = tile.get("center_lon") or tile.get("center", {}).get("lon")
        tile_id = tile.get("id")
        if lat and lon and tile_id:
            for phrase in search_phrases:
                tasks.append({
                    "tile_id": tile_id,
                    "search_phrase": phrase,
                    "latitude": LatScale6(lat),
                    "longitude": LonScale6(lon)
                })

    # Sort by tile_id then phrase for stability
    tasks.sort(key=lambda x: (x["tile_id"], x["search_phrase"]))

    from ...models.campaigns.mission import MissionTask
    discovery_gen = paths.campaign(campaign_name).queue("discovery-gen")
    mission_usv_path = discovery_gen.master # Root/mission.usv
    mission_tasks = [MissionTask(**t) for t in tasks]
    MissionTask.save_usv_with_datapackage(mission_tasks, mission_usv_path, "mission")

    # 5. Filter for Pending Tasks (The Frontier)
    console.print(f"[bold]Filtering against ScrapeIndex (TTL: {ttl_days} days) to find the frontier...[/bold]")
    scrape_index = ScrapeIndex()
    
    if debug:
        temp_manifest = discovery_gen.path / "temp" / "scraped_manifest.usv"
        count = scrape_index.generate_diagnostic_manifest(temp_manifest)
        console.print(f"[dim]  Generated diagnostic manifest with {count} items at {temp_manifest}[/dim]")

    pending_tasks = []
    
    match_count = 0
    skipped_unproductive = 0
    checked = 0
    for t in tasks:
        checked += 1
        match = scrape_index.is_tile_scraped(t["search_phrase"], t["tile_id"], ttl_days=ttl_days)
        
        # If it's NOT a match (it's unscraped or stale), we might want it
        if not match:
            # But we must check if it was EVER scraped and found 0 items
            forever_match = scrape_index.is_tile_scraped(t["search_phrase"], t["tile_id"], ttl_days=None)
            if forever_match and forever_match.items_found == 0:
                skipped_unproductive += 1
                continue
                
            # Double check with area bounds to be safe
            lat, lon = t["latitude"], t["longitude"]
            bounds = {"lat_min": lat-0.05, "lat_max": lat+0.05, "lon_min": lon-0.05, "lon_max": lon+0.05}
            area_match_res = scrape_index.is_area_scraped(t["search_phrase"], bounds, ttl_days=ttl_days, overlap_threshold_percent=90.0)
            if area_match_res:
                # Unproductive check for area matches
                area_match, _ = area_match_res
                if area_match.items_found == 0:
                    skipped_unproductive += 1
                    continue
                match = area_match
            
            if not match:
                pending_tasks.append(t)
            else:
                match_count += 1
        else:
            match_count += 1

    console.print(f"[dim]  Checked {checked} tasks.[/dim]")
    if match_count > 0:
        console.print(f"[green]  Successfully identified {match_count} previously scraped tiles.[/green]")
    if skipped_unproductive > 0:
        console.print(f"[yellow]  Skipped {skipped_unproductive} previously unproductive tiles (0 results).[/yellow]")

    frontier_path = discovery_gen.pending / "frontier.usv"
    frontier_model_tasks = [MissionTask(**t) for t in pending_tasks]
    MissionTask.save_usv_with_datapackage(frontier_model_tasks, frontier_path, "frontier")

    # 6. Reset State
    state_path = campaign_dir / "mission_state.toml"
    with open(state_path, "w") as f:
        toml.dump({"last_offset": 0}, f)

    console.print("[bold green]Mission prepared![/bold green]")
    console.print(f"  Total mission tasks: [cyan]{len(tasks)}[/cyan]")
    console.print(f"  [bold yellow]Pending frontier: {len(pending_tasks)}[/bold yellow]")
    console.print(f"  Saved master to: {mission_usv_path}")
    console.print(f"  Saved frontier to: {frontier_path}")
    console.print("[dim]Offset reset to 0.[/dim]")

@app.command(name="create-batch")
def create_batch(
    campaign_name: Annotated[Optional[str], typer.Argument(help="The name of the campaign.")] = None,
    name: str = typer.Option("batch", help="Name of the batch (e.g., 'canary')"),
    limit: int = typer.Option(50, help="Number of items to include in the batch"),
    offset: int = typer.Option(0, help="Number of items to skip from the frontier"),
    query: Optional[str] = typer.Option(None, help="Manual task entry (format: 'tile_id;phrase;lat;lon')"),
) -> None:
    """
    Creates a named batch subset from the pending frontier for controlled rollout.
    """
    if campaign_name is None:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    discovery_gen = paths.campaign(campaign_name).queue("discovery-gen")
    frontier_path = discovery_gen.pending / "frontier.usv"
    batch_dir = discovery_gen.pending / "batches"
    batch_path = batch_dir / f"{name}.usv"

    from ...models.campaigns.mission import MissionTask
    
    tasks: List[MissionTask] = []

    if query:
        # Manual Mode
        parts = query.split(";")
        if len(parts) == 4:
            from ...core.geo_types import LatScale6, LonScale6
            tasks.append(MissionTask(
                tile_id=parts[0],
                search_phrase=parts[1],
                latitude=LatScale6(float(parts[2])),
                longitude=LonScale6(float(parts[3]))
            ))
        else:
            console.print("[red]Invalid query format. Expected 'tile_id;phrase;lat;lon'[/red]")
            raise typer.Exit(1)
    else:
        # Frontier Mode
        if not frontier_path.exists():
            console.print(f"[red]Frontier file not found: {frontier_path}. Run 'prepare-mission' first.[/red]")
            raise typer.Exit(1)

        from ...core.scrape_index import ScrapeIndex
        scrape_index = ScrapeIndex()
        
        skipped_count = 0
        passed_offset = 0
        
        with open(frontier_path, "r", encoding="utf-8") as f:
            for line in f:
                if len(tasks) >= limit:
                    break
                if line.strip():
                    try:
                        task = MissionTask.from_usv(line)
                        match = scrape_index.is_tile_scraped(task.search_phrase, task.tile_id, ttl_days=30)
                        if not match:
                            if passed_offset < offset:
                                passed_offset += 1
                                continue
                            tasks.append(task)
                        else:
                            skipped_count += 1
                    except Exception:
                        continue

        if skipped_count > 0:
            console.print(f"[dim]  Skipped {skipped_count} items that are already recent/valid in index.[/dim]")

    if not tasks:
        console.print("[yellow]No tasks found in frontier to batch.[/yellow]")
        return

    MissionTask.save_usv_with_datapackage(tasks, batch_path, name)
    console.print(f"[bold green]Batch '{name}' created![/bold green]")
    console.print(f"  Included {len(tasks)} tasks.")
    console.print(f"  Saved to: {batch_path}")

@app.command(name="build-mission-index")
def build_mission_index(
    campaign_name: Annotated[Optional[str], typer.Argument(help="The name of the campaign.")] = None,
    batch: Optional[str] = typer.Option(None, help="Specific batch name to activate (from pending/batches/)"),
) -> None:
    """
    Explodes a mission list into the Active Task Pool (discovery-gen/completed/).
    Defaults to Root/mission.usv if no batch is specified.
    """
    if campaign_name is None:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    discovery_gen = paths.campaign(campaign_name).queue("discovery-gen")
    
    if batch:
        source_path = discovery_gen.pending / "batches" / f"{batch}.usv"
    else:
        source_path = discovery_gen.master

    target_index_dir = discovery_gen.completed

    if not source_path.exists():
        console.print(f"[red]Source list not found: {source_path}[/red]")
        raise typer.Exit(1)

    from ...core.sharding import get_geo_shard
    from ...models.campaigns.mission import MissionTask
    
    tasks = []
    with open(source_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    task = MissionTask.from_usv(line)
                    tasks.append(task)
                except Exception as e:
                    logger.warning(f"Failed to parse mission line: {e}")

    # Build index datapackage for discovery-gen active pool
    MissionTask.save_datapackage(target_index_dir, "discovery-gen-active", "**/*.usv")

    console.print(f"Activating {len(tasks)} tasks from {source_path.name} into {target_index_dir}...")
    
    count = 0
    for task in tasks:
        tile_id = task.tile_id
        phrase = task.search_phrase
        lat_str, lon_str = tile_id.split("_")
        lat_shard = get_geo_shard(float(task.latitude))
        
        # discovery-gen/completed/2/25.0/-79.9/phrase.usv
        tile_dir = target_index_dir / lat_shard / lat_str / lon_str
        tile_dir.mkdir(parents=True, exist_ok=True)
        
        target_path = tile_dir / f"{slugify(phrase)}.usv"
        
        if not target_path.exists():
            with open(target_path, "w") as f:
                # Use standard model-based serialization
                f.write(task.to_usv())
            count += 1

    console.print("[bold green]Mission index built![/bold green]")
    console.print(f"  Created {count} active task files.")

@app.command(name="queue-mission")
def queue_mission(
    campaign_name: Annotated[Optional[str], typer.Argument(help="The name of the campaign.")] = None,
) -> None:
    """
    Reports the status of the Discovery Generation queue.
    """
    if campaign_name is None:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    discovery_gen = paths.campaign(campaign_name).queue("discovery-gen")
    
    # 1. Check Master
    if not discovery_gen.master.exists():
        console.print("[red]Mission not prepared. Run 'prepare-mission' first.[/red]")
        return

    master_count = sum(1 for _ in open(discovery_gen.master))
    
    # 2. Check Frontier
    frontier_count = 0
    if (discovery_gen.pending / "frontier.usv").exists():
        frontier_count = sum(1 for _ in open(discovery_gen.pending / "frontier.usv"))

    # 3. Check Active Pool
    active_count = 0
    if discovery_gen.completed.exists():
        active_count = len(list(discovery_gen.completed.glob("**/*.usv")))

    console.print(f"[bold cyan]Discovery Queue Status: {campaign_name}[/bold cyan]")
    console.print(f"  Master Mission: {master_count} tiles")
    console.print(f"  Pending Frontier: {frontier_count} tiles")
    console.print(f"  Active Task Pool: {active_count} tiles")
    
    if active_count == 0 and frontier_count > 0:
        console.print("\n[yellow]Tip: Run 'create-batch' and 'build-mission-index' to activate tasks.[/yellow]")

@app.command()
def achieve_goal(
    goal_emails: int = typer.Option(10, "--emails"),
    campaign_name: Optional[str] = typer.Argument(None),
    force: bool = typer.Option(False, "--force", "-f"),
    ttl_days: int = typer.Option(30, "--ttl-days"),
    proximity_miles: float = typer.Option(10.0, "--proximity"),
    grid_mode: bool = typer.Option(False, "--grid"),
) -> None:
    if campaign_name is None:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[red]Campaign directory not found for {campaign_name}[/red]")
        raise typer.Exit(1)

    with open(campaign_dir / "config.toml", "r") as f:
        config = toml.load(f)
    
    prospecting_config = config.get("prospecting", {})
    if proximity_miles == 10.0 and "proximity" in prospecting_config:
        proximity_miles = float(prospecting_config["proximity"])
        console.print(f"[dim]Using proximity from campaign config: {proximity_miles} mi[/dim]")

    search_phrases = prospecting_config.get("queries", [])
    grid_tiles = None
    if grid_mode:
        grid_file = campaign_dir / "exports" / "target-areas.json"
        if grid_file.exists():
            with open(grid_file, "r") as f:
                grid_tiles = json.load(f)

    existing_companies_map = {c.domain: c.slug for c in Company.get_all() if c.domain and c.slug}
    asyncio.run(pipeline(
        locations=[], search_phrases=search_phrases, goal_emails=goal_emails, headed=False, devtools=False,
        campaign_name=campaign_name, existing_companies_map=existing_companies_map, overlap_threshold_percent=30.0,
        zoom_out_button_selector="div#zoomOutButton", panning_distance_miles=8, initial_zoom_out_level=3,
        omit_zoom_feature=False, force=force, ttl_days=ttl_days, debug=False, console=console,
        browser_width=2000, browser_height=2000, location_prospects_index=LocationProspectsIndex(campaign_name),
        use_cloud_queue=False, max_proximity_miles=proximity_miles, grid_tiles=grid_tiles
    ))