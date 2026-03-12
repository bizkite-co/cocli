import typer
import asyncio
import logging
import toml
import json
import csv
from typing import Optional, List, Dict, Any, cast, Annotated
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from playwright.async_api import async_playwright

from cocli.core.paths import paths
from cocli.core.config import get_campaign_dir, get_campaign, get_enrichment_service_url

from cocli.core.scrape_index import ScrapeIndex
from cocli.core.text_utils import slugify
from cocli.core.location_prospects_index import LocationProspectsIndex
from cocli.core.queue.factory import get_queue_manager
from cocli.planning.generate_grid import get_campaign_grid_tiles
from cocli.models.campaigns.queues.gm_list import ScrapeTask
from cocli.models.companies.company import Company
from cocli.scrapers.google_maps import scrape_google_maps
from cocli.scrapers.google_maps_details import scrape_google_maps_details
from cocli.compilers.website_compiler import WebsiteCompiler
from cocli.core.enrichment import enrich_company_website
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.models.campaigns.indexes.google_maps_venue import GoogleMapsVenue

logger = logging.getLogger(__name__)
console = Console()
app = typer.Typer(no_args_is_help=True)

async def pipeline(
    locations: list[str],
    search_phrases: list[str],
    goal_limit: int,
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
    resource_discovery: bool = False,
    prospect_type: str = "prospect",
) -> None:
    
    queue_manager = get_queue_manager(f"{campaign_name}_enrichment", use_cloud=use_cloud_queue)
    stop_event = asyncio.Event()
    results_found_count = 0
    
    # --- PRE-FLIGHT: Ensure output directory and file are ready ---
    model_cls = GoogleMapsVenue if prospect_type == "venue" else GoogleMapsProspect
    checkpoint_path = paths.campaign(campaign_name).index(model_cls.INDEX_NAME).checkpoint
    if prospect_type == "venue":
        checkpoint_path = paths.campaign(campaign_name).index(model_cls.INDEX_NAME).path / "venues.checkpoint.usv"

    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    if not checkpoint_path.exists():
        checkpoint_path.touch()

    # Resolve seeding location
    location_param = {"latitude": "0", "longitude": "0"}
    if locations:
        location_param = {"city": locations[0]}
    elif target_locations:
        location_param = target_locations[0]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        goal_task_id = progress.add_task(f"[cyan]Finding {prospect_type}s...", total=goal_limit)
        scan_task_id = progress.add_task("[dim]Scanning Google Maps...", total=None)
        
        launch_proxy = {"server": proxy_url} if proxy_url else None

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=not headed,
                devtools=devtools,
                proxy=cast(Any, launch_proxy),
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )
            
            async def consumer_task() -> None: 
                nonlocal results_found_count
                enrichment_url = get_enrichment_service_url()
                use_cloud_enrichment = enrichment_url != "http://localhost:8000"
                consumer_context = await browser.new_context() if not use_cloud_enrichment else None
                compiler = WebsiteCompiler()
                
                while not stop_event.is_set():
                    messages = await asyncio.to_thread(queue_manager.poll, batch_size=1)
                    if not messages:
                        await asyncio.sleep(2)
                        continue
                    
                    for msg in messages:
                        if stop_event.is_set():
                            break
                        progress.update(scan_task_id, description=f"[dim]Enriching: {msg.domain}[/dim]")
                        
                        website_data = None
                        if not use_cloud_enrichment and consumer_context:
                            dummy_company = Company(name=msg.domain, domain=msg.domain, slug=msg.company_slug)
                            try:
                                website_data = await enrich_company_website(browser=consumer_context, company=dummy_company, force=msg.force_refresh, ttl_days=msg.ttl_days)
                            except Exception:
                                pass
                        
                        if prospect_type == "prospect" and website_data and website_data.email:
                            results_found_count += 1
                            progress.advance(goal_task_id)
                            if results_found_count >= goal_limit:
                                stop_event.set()
                        
                        queue_manager.ack(msg)
                
                compiler.save_audit_report()

            async def producer_task(existing_companies_map: Dict[str, str]) -> None: 
                from ...models.campaigns.queues.base import QueueMessage
                from ...scrapers.resource_analyzer import is_likely_non_commercial
                nonlocal results_found_count
                
                enrichment_queue = get_queue_manager(f"{campaign_name}_enrichment", use_cloud=use_cloud_queue)

                prospect_generator = scrape_google_maps(
                    browser=browser, location_param=location_param,
                    search_strings=search_phrases, campaign_name=campaign_name, grid_tiles=grid_tiles,
                    force_refresh=force, ttl_days=ttl_days, debug=debug, max_proximity_miles=max_proximity_miles,
                    overlap_threshold_percent=overlap_threshold_percent
                )
                
                async for list_item in prospect_generator:
                    if stop_event.is_set():
                        break
                    
                    # --- FAST FILTERING ---
                    is_venue_match = is_likely_non_commercial(list_item.category or "") or \
                                     any(k in list_item.name.lower() for k in ["park", "library", "center", "museum", "gallery"])
                    
                    if resource_discovery and not is_venue_match:
                        continue

                    progress.update(scan_task_id, description=f"[bold blue]Detailing:[/bold blue] {list_item.name}")
                    
                    page = await browser.new_page()
                    try:
                        detailed_data_raw = await scrape_google_maps_details(
                            page=page, place_id=list_item.place_id, campaign_name=campaign_name,
                            name=list_item.name, company_slug=list_item.company_slug, debug=debug
                        )
                        
                        if detailed_data_raw:
                            # Transform to correct domain model
                            from cocli.models.campaigns.indexes.google_maps_raw import GoogleMapsRawResult
                            raw_typed = cast(GoogleMapsRawResult, detailed_data_raw)
                            detailed_data = model_cls.from_raw(raw_typed)
                            
                            # For VENUES, we capture and increment goal immediately after detailing
                            is_val = getattr(detailed_data, "is_value_resource", False)
                            if prospect_type == "venue" and (not resource_discovery or is_val):
                                # Cast to Any to satisfy mypy's strict class-method checking on Union types
                                cast(Any, model_cls).append_to_checkpoint(campaign_name, detailed_data)
                                console.print(f"[bold green]VENUE CAPTURED:[/bold green] {detailed_data.name}")
                                results_found_count += 1
                                progress.advance(goal_task_id)
                                if results_found_count >= goal_limit:
                                    stop_event.set()

                            if detailed_data.domain:
                                enrichment_queue.push(QueueMessage(
                                    domain=detailed_data.domain, company_slug=detailed_data.company_slug,
                                    campaign_name=campaign_name, force_refresh=force, ack_token=None
                                ))
                    finally:
                        await page.close()
                    await asyncio.sleep(0.1)

            try:
                async with asyncio.timeout(1800): # 30-minute watchdog
                    await asyncio.gather(producer_task(existing_companies_map), consumer_task())
            except asyncio.TimeoutError:
                console.print("[yellow]Pipeline timed out after 30 minutes.[/yellow]")
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
    offset: Optional[int] = typer.Option(None, help="Manual override for the frontier offset"),
    query: Optional[str] = typer.Option(None, help="Manual task entry (format: 'tile_id;phrase;lat;lon')"),
) -> None:
    """
    Creates a named batch subset from the pending frontier for controlled rollout.
    Sequential batches automatically track their offset in mission_state.toml.
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

    dg = paths.campaign(campaign_name).queue("discovery-gen", ensure=True)
    
    frontier_path = dg.pending / "frontier.usv"
    batch_dir = dg.pending / "batches"
    batch_path = batch_dir / f"{name}.usv"
    state_path = campaign_dir / "mission_state.toml"

    from ...models.campaigns.mission import MissionTask
    
    tasks: List[MissionTask] = []

    if query:
        # Manual Mode (Ignores offsets/state)
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

        # 1. Resolve Offset
        current_offset = 0
        if offset is not None:
            current_offset = offset
        elif state_path.exists():
            state = toml.load(state_path)
            current_offset = state.get("last_offset", 0)

        from ...core.scrape_index import ScrapeIndex
        scrape_index = ScrapeIndex()
        
        skipped_count = 0
        
        with open(frontier_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i < current_offset:
                    continue
                if len(tasks) >= limit:
                    break
                if line.strip():
                    try:
                        task = MissionTask.from_usv(line)
                        # Ensure we don't batch something that was JUST scraped (e.g. by another node)
                        match = scrape_index.is_tile_scraped(task.search_phrase, task.tile_id, ttl_days=30)
                        if not match:
                            tasks.append(task)
                        else:
                            skipped_count += 1
                    except Exception:
                        continue

        if not tasks:
            console.print("[yellow]No new tasks found in frontier to batch.[/yellow]")
            return

        # 2. Update State (Only in Frontier Mode)
        new_offset = current_offset + len(tasks) + skipped_count
        with open(state_path, "w") as f:
            toml.dump({"last_offset": new_offset}, f)

        console.print(f"  Start Offset: {current_offset}")
        console.print(f"  Skipped:      {skipped_count} (already valid in index)")
        console.print(f"  Next Offset:  {new_offset}")

    # 3. Save Batch
    MissionTask.save_usv_with_datapackage(tasks, batch_path, name)
    console.print(f"[bold green]Batch '{name}' created![/bold green]")
    console.print(f"  Included:     {len(tasks)} tasks")
    console.print(f"  Saved to:     {batch_path}")

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

    discovery_gen = paths.campaign(campaign_name).queue("discovery-gen", ensure=True)
    
    if batch:
        source_path = discovery_gen.pending / "batches" / f"{batch}.usv"
    else:
        source_path = discovery_gen.master

    target_index_dir = discovery_gen.completed
    target_index_dir.mkdir(parents=True, exist_ok=True)

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

@app.command(name="monitor-batch")
def monitor_batch(
    campaign_name: Annotated[Optional[str], typer.Argument(help="The name of the campaign.")] = None,
    name: str = typer.Option("canary_500", help="Name of the batch to monitor."),
    recent: bool = typer.Option(False, "--recent", help="Only show recent or pending tasks."),
    cluster: bool = typer.Option(False, "--cluster", help="Run report remotely on the cluster Hub for real-time data."),
) -> None:
    """
    Monitor the progress of a discovery batch.
    Use --cluster to see live results from the gossip network authority (cocli5x1.pi).
    """
    if campaign_name is None:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    if cluster:
        # Remote execution on Hub
        import subprocess
        hub = "cocli5x1.pi"
        cmd = f"docker exec cocli-supervisor cocli campaign monitor-batch {campaign_name} --name {name}"
        if recent:
            cmd += " --recent"
        
        console.print(f"[bold cyan]Querying Cluster Authority: {hub}...[/bold cyan]")
        try:
            subprocess.run(["ssh", f"mstouffer@{hub}", cmd], check=True)
        except Exception as e:
            console.print(f"[red]Could not reach Hub: {e}[/red]")
        return

    discovery_gen = paths.campaign(campaign_name).queue("discovery-gen")
    batch_file = discovery_gen.pending / "batches" / f"{name}.usv"
    results_dir = paths.campaign(campaign_name).queue("gm-list").completed / "results"
    pending_queue_dir = paths.campaign(campaign_name).queue("gm-list").pending

    if not batch_file.exists():
        console.print(f"[red]Batch file not found: {batch_file}[/red]")
        raise typer.Exit(1)

    from ...models.campaigns.mission import MissionTask
    from ...core.sharding import get_geo_shard, get_grid_tile_id
    from ...core.text_utils import slugify
    from rich.table import Table
    from datetime import datetime, UTC, timedelta
    import json

    # 1. Load Batch
    tasks: List[MissionTask] = []
    with open(batch_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    tasks.append(MissionTask.from_usv(line))
                except Exception:
                    continue

    if not tasks:
        console.print("[yellow]No valid tasks found in batch.[/yellow]")
        return

    # 2. Build Status Table
    table = Table(title=f"Monitoring Batch: {name} ({campaign_name})")
    table.add_column("Tile ID", style="cyan")
    table.add_column("Phrase", style="magenta")
    table.add_column("Status", justify="center")
    table.add_column("Details", style="dim")

    completed_count = 0
    in_progress_count = 0
    pending_count = 0
    stale_count = 0

    now = datetime.now(UTC)
    # Threshold for 'RECENT': Completions within the last 24 hours
    threshold = now - timedelta(hours=24)

    for task in tasks:
        lat_shard = get_geo_shard(float(task.latitude))
        grid_id = get_grid_tile_id(float(task.latitude), float(task.longitude))
        lat_tile, lon_tile = grid_id.split("_")
        phrase_slug = slugify(task.search_phrase)
        
        # Check for results (Completed)
        receipt_file = results_dir / lat_shard / lat_tile / lon_tile / f"{phrase_slug}.json"
        
        # Check for lease (In Progress)
        task_sub_path = f"{lat_shard}/{lat_tile}/{lon_tile}/{phrase_slug}.usv"
        lease_file = pending_queue_dir / task_sub_path / "lease.json"
        
        status = "[white]PENDING[/white]"
        details = "-"
        is_stale = False
        
        if receipt_file.exists():
            try:
                with open(receipt_file, "r") as f:
                    data = json.load(f)
                    count = data.get("result_count", 0)
                    worker = data.get("worker_id", "unknown")
                    comp_at_str = data.get("completed_at")
                    
                    if comp_at_str:
                        comp_at = datetime.fromisoformat(comp_at_str.replace("Z", "+00:00"))
                        if comp_at > threshold:
                            status = "[bold green]DONE[/bold green]"
                            details = f"[bold]{count}[/bold] by {worker} (RECENT)"
                            completed_count += 1
                        else:
                            status = "[blue]STALE[/blue]"
                            details = f"{count} by {worker} (Pending Refresh: {comp_at.strftime('%m-%d')})"
                            is_stale = True
                            stale_count += 1
                    else:
                        status = "[green]DONE[/green]"
                        details = f"{count} by {worker}"
                        completed_count += 1
            except Exception:
                status = "[green]DONE[/green]"
                details = "Result exists"
                completed_count += 1
        elif lease_file.exists():
            status = "[yellow]ACTIVE[/yellow]"
            try:
                with open(lease_file, "r") as f:
                    data = json.load(f)
                    worker = data.get("worker_id", "unknown")
                    details = f"Worker: {worker}"
            except Exception:
                details = "Leased"
            in_progress_count += 1
        else:
            pending_count += 1

        if not recent or not is_stale:
            table.add_row(task.tile_id, task.search_phrase, status, details)

    console.print(table)
    
    # Summary
    console.print("\n[bold]Summary:[/bold]")
    console.print(f"  [bold green]Recent Done:  {completed_count}[/bold green]")
    console.print(f"  [blue]Stale (Pending Refresh):  {stale_count}[/blue]")
    console.print(f"  [yellow]Active:       {in_progress_count}[/yellow]")
    console.print(f"  [white]Pending:      {pending_count}[/white]")
    console.print(f"  Total:        {len(tasks)}")

@app.command(name="discover-venues")
def discover_venues(
    campaign_name: Optional[str] = typer.Argument(None),
    goal_limit: int = typer.Option(20, "--limit", "-l", help="Number of venues to find."),
    force: bool = typer.Option(False, "--force", "-f"),
    headed: bool = typer.Option(False, "--headed", help="Run with a visible browser window."),
) -> None:
    """
    Discovers local community venues and institutions via Google Maps.
    Populates the events discovery pipeline.
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

    with open(campaign_dir / "config.toml", "r") as f:
        config = toml.load(f)
    
    prospecting_config = config.get("prospecting", {})
    search_phrases = prospecting_config.get("queries", [])
    locations = prospecting_config.get("locations", [])

    if not search_phrases:
        console.print("[yellow]No queries found in campaign config.[/yellow]")
        return

    if locations:
        console.print(f"[dim]Seeding search from location: {locations[0]}[/dim]")

    from cocli.core.paths import paths
    from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
    checkpoint_path = paths.campaign(campaign_name).index(GoogleMapsProspect.INDEX_NAME).path / "venues.checkpoint.usv"
    console.print(f"[bold blue]Starting Venue Discovery for {campaign_name}...[/bold blue]")
    console.print(f"[dim]Output file: {checkpoint_path}[/dim]\n")
    
    # We leverage the existing pipeline but focus on venues
    asyncio.run(pipeline(
        locations=[], 
        search_phrases=search_phrases, 
        goal_limit=goal_limit, 
        headed=headed, 
        devtools=False,
        campaign_name=campaign_name, 
        existing_companies_map={}, 
        overlap_threshold_percent=30.0,
        zoom_out_button_selector="div#zoomOutButton", 
        panning_distance_miles=8, 
        initial_zoom_out_level=3,
        omit_zoom_feature=False, 
        force=force, 
        ttl_days=30, 
        debug=False, 
        console=console,
        browser_width=2000, 
        browser_height=2000, 
        location_prospects_index=LocationProspectsIndex(campaign_name),
        use_cloud_queue=False, 
        max_proximity_miles=10.0, 
        grid_tiles=None,
        resource_discovery=True,
        target_locations=[{"city": loc} for loc in locations] if locations else None,
        prospect_type="venue"
    ))

@app.command()
def achieve_goal(
    goal_limit: int = typer.Option(10, "--emails", "--limit", help="Number of resources (or emails) to find before stopping."),
    campaign_name: Optional[str] = typer.Argument(None),
    force: bool = typer.Option(False, "--force", "-f"),
    ttl_days: int = typer.Option(30, "--ttl-days"),
    proximity_miles: float = typer.Option(10.0, "--proximity"),
    grid_mode: bool = typer.Option(False, "--grid"),
    resource_discovery: bool = typer.Option(False, "--resource-discovery", help="Prioritize and filter for public/value resources."),
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

    # Resolve headed mode
    is_headed = config.get("prospecting", {}).get("headed", False)

    # Build existing companies map with progress
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as scan_progress:
        task = scan_progress.add_task("Scanning existing database...", total=None)
        existing_companies_map = {}
        loaded = 0
        skipped = 0
        for c in Company.get_all():
            if c:
                loaded += 1
                if c.domain and c.slug:
                    existing_companies_map[c.domain] = c.slug
            else:
                skipped += 1
            if (loaded + skipped) % 50 == 0:
                scan_progress.update(task, description=f"Scanning database... ({loaded} loaded, {skipped} skipped)")

    asyncio.run(pipeline(
        locations=[], search_phrases=search_phrases, goal_limit=goal_limit, headed=is_headed, devtools=False,
        campaign_name=campaign_name, existing_companies_map=existing_companies_map, overlap_threshold_percent=30.0,
        zoom_out_button_selector="div#zoomOutButton", panning_distance_miles=8, initial_zoom_out_level=3,
        omit_zoom_feature=False, force=force, ttl_days=ttl_days, debug=False, console=console,
        browser_width=2000, browser_height=2000, location_prospects_index=LocationProspectsIndex(campaign_name),
        use_cloud_queue=False, max_proximity_miles=proximity_miles, grid_tiles=grid_tiles,
        resource_discovery=resource_discovery,
        prospect_type="prospect"
    ))
