import typer
import asyncio
import logging
import toml
import json
import csv
import httpx
from pathlib import Path
from typing import Optional, List, Dict, Any, cast
from rich.console import Console
from playwright.async_api import async_playwright
import yaml

from cocli.core.config import get_companies_dir, get_campaign_dir, get_campaign, get_enrichment_service_url
from cocli.core.importing import import_prospect
from cocli.core.prospects_csv_manager import ProspectsIndexManager
from cocli.core.scrape_index import ScrapeIndex
from cocli.core.text_utils import slugify
from cocli.core.location_prospects_index import LocationProspectsIndex
from cocli.core.queue.factory import get_queue_manager
from cocli.planning.generate_grid import generate_global_grid, DEFAULT_GRID_STEP_DEG
from cocli.models.queue import QueueMessage
from cocli.models.scrape_task import ScrapeTask
from cocli.models.google_maps_prospect import GoogleMapsProspect
from cocli.models.company import Company
from cocli.models.website import Website
from cocli.scrapers.google_maps import scrape_google_maps
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
            
            while not stop_event.is_set():
                messages = queue_manager.poll(batch_size=1)
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
                        WebsiteCompiler().compile(company_dir)
                        if website_data.email:
                            emails_found_count += 1
                        if emails_found_count >= goal_emails:
                            stop_event.set()
                        queue_manager.ack(msg)
        async def producer_task(existing_companies_map: Dict[str, str]) -> None: 
            csv_manager = ProspectsIndexManager(campaign_name)

            async def process_prospect_item(prospect_data: GoogleMapsProspect, location_name: str) -> None: 
                csv_manager.append_prospect(prospect_data)
                company = import_prospect(prospect_data, campaign=campaign_name)
                if company and company.domain and not company.email:
                    msg = QueueMessage(domain=company.domain, company_slug=company.slug, campaign_name=campaign_name, force_refresh=force, ttl_days=ttl_days, ack_token=None)
                    queue_manager.push(msg)

            prospect_generator = scrape_google_maps(
                browser=browser, location_param={"latitude": "0", "longitude": "0"},
                search_strings=search_phrases, campaign_name=campaign_name, grid_tiles=grid_tiles,
                force_refresh=force, ttl_days=ttl_days, debug=debug, max_proximity_miles=max_proximity_miles,
                overlap_threshold_percent=overlap_threshold_percent
            )
            async for prospect_data in prospect_generator:
                if stop_event.is_set():
                    break
                await process_prospect_item(prospect_data, "Grid Scan")
                await asyncio.sleep(0.01)

        await asyncio.gather(producer_task(existing_companies_map), consumer_task())

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
    grid_file = campaign_dir / "exports" / "target-areas.json"
    tasks_to_queue = []
    total_combinations = 0
    
    if grid_file.exists():
        scrape_index = ScrapeIndex()
        with open(grid_file, 'r') as f:
            grid_tiles = json.load(f)
        
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
    grid_file = campaign_dir / "exports" / "target-areas.json"
    tasks_to_queue = []
    
    if grid_file.exists():
        scrape_index = ScrapeIndex()
        with open(grid_file, 'r') as f:
            grid_tiles = json.load(f)
        
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
            from cocli.models.scrape_task import ScrapeTask
            queue_manager.push(ScrapeTask(**t_dict))
        console.print(f"[bold green]Successfully queued {len(tasks_to_queue)} tasks.[/bold green]")
    else:
        console.print("[yellow]No tasks to queue.[/yellow]")

@app.command(name="prepare-mission")
def prepare_mission(
    campaign_name: Optional[str] = typer.Argument(None),
) -> None:
    """
    Generates a deterministic master task list (mission.json) for the campaign.
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
        csv_path = campaign_dir / target_locations_csv
        if csv_path.exists():
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    lat, lon = row.get("lat"), row.get("lon")
                    if lat and lon:
                        target_locations.append({
                            "name": row.get("name") or row.get("city"),
                            "lat": float(lat),
                            "lon": float(lon)
                        })

    # 3. Generate Grid
    console.print(f"[bold]Generating grid for {len(target_locations)} locations (Radius: {proximity_miles} mi)...[/bold]")
    all_tiles: Dict[str, Any] = {}
    for loc in target_locations:
        tiles = generate_global_grid(loc["lat"], loc["lon"], proximity_miles, step_deg=DEFAULT_GRID_STEP_DEG)
        for tile in tiles:
            if tile["id"] not in all_tiles:
                all_tiles[tile["id"]] = tile

    unique_tiles = list(all_tiles.values())
    
    # Save target-areas.json for compatibility
    export_dir = campaign_dir / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    with open(export_dir / "target-areas.json", "w") as f:
        json.dump(unique_tiles, f, indent=2)

    # 4. Build Deterministic Task List
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
                    "latitude": float(lat),
                    "longitude": float(lon)
                })

    # Sort by tile_id then phrase for stability
    tasks.sort(key=lambda x: (x["tile_id"], x["search_phrase"]))

    mission_path = campaign_dir / "mission.json"
    with open(mission_path, "w") as f:
        json.dump(tasks, f, indent=2)

    # 5. Filter for Pending Tasks (The Frontier)
    console.print("[bold]Filtering against ScrapeIndex to find the frontier...[/bold]")
    scrape_index = ScrapeIndex()
    pending_tasks = []
    
    for t in tasks:
        if not scrape_index.is_tile_scraped(t["search_phrase"], t["tile_id"], ttl_days=30):
            # Double check with area bounds to be safe
            lat, lon = t["latitude"], t["longitude"]
            bounds = {"lat_min": lat-0.05, "lat_max": lat+0.05, "lon_min": lon-0.05, "lon_max": lon+0.05}
            if not scrape_index.is_area_scraped(t["search_phrase"], bounds, overlap_threshold_percent=90.0):
                pending_tasks.append(t)

    pending_csv_path = campaign_dir / "indexes" / "pending_scrape_total.csv"
    pending_csv_path.parent.mkdir(exist_ok=True)
    
    with open(pending_csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["tile_id", "search_phrase", "latitude", "longitude"])
        writer.writeheader()
        writer.writerows(pending_tasks)

    # 6. Reset State
    state_path = campaign_dir / "mission_state.toml"
    with open(state_path, "w") as f:
        toml.dump({"last_offset": 0}, f)

    console.print("[bold green]Mission prepared![/bold green]")
    console.print(f"  Total mission tasks: [cyan]{len(tasks)}[/cyan]")
    console.print(f"  [bold yellow]Pending (unscraped): {len(pending_tasks)}[/bold yellow]")
    console.print(f"  Saved frontier to: {pending_csv_path}")
    console.print("[dim]Offset reset to 0.[/dim]")

@app.command(name="build-mission-index")
def build_mission_index(
    campaign_name: Optional[str] = typer.Argument(None),
) -> None:
    """
    Explodes the mission into a nested file-per-object Target Tile index.
    """
    if campaign_name is None:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[red]Campaign directory not found for {campaign_name}.[/red]")
        raise typer.Exit(1)
        
    mission_path = campaign_dir / "mission.json"
    target_index_dir = campaign_dir / "indexes" / "target-tiles"

    if not mission_path.exists():
        console.print("[red]Mission list not found. Run 'prepare-mission' first.[/red]")
        raise typer.Exit(1)

    with open(mission_path, "r") as f:
        tasks = json.load(f)

    console.print(f"Exploding {len(tasks)} tasks into {target_index_dir}...")
    
    count = 0
    for t in tasks:
        tile_id = t["tile_id"]
        phrase = t["search_phrase"]
        lat_str, lon_str = tile_id.split("_")
        
        # target-tiles/30.2/-97.7/phrase.csv
        tile_dir = target_index_dir / lat_str / lon_str
        tile_dir.mkdir(parents=True, exist_ok=True)
        
        target_path = tile_dir / f"{slugify(phrase)}.csv"
        
        # Write minimal metadata
        if not target_path.exists():
            with open(target_path, "w") as f:
                f.write("latitude,longitude\n")
                f.write(f"{t['latitude']},{t['longitude']}\n")
            count += 1

    console.print("[bold green]Mission index built![/bold green]")
    console.print(f"  Created {count} target tile files.")

@app.command(name="queue-mission")
def queue_mission(
    campaign_name: Optional[str] = typer.Argument(None),
    limit: int = typer.Option(100, help="Number of tasks to enqueue."),
    sync: bool = typer.Option(True, help="Automatically sync scraped-tiles from S3 before enqueuing."),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """
    Idempotently enqueues unscraped tasks by comparing the Target Index and the Global Scraped Index.
    """
    if campaign_name is None:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    # 0. Auto-Sync State
    if sync:
        from cocli.commands.smart_sync import run_smart_sync
        from cocli.core.config import load_campaign_config, get_cocli_base_dir
        
        console.print("[bold blue]Syncing scraped-tiles from S3...[/bold blue]")
        config = load_campaign_config(campaign_name)
        aws_config = config.get("aws", {})
        bucket_name = aws_config.get("cocli_data_bucket_name") or f"cocli-data-{campaign_name}"
        data_dir = get_cocli_base_dir()
        
        try:
            run_smart_sync(
                "scraped-tiles", 
                bucket_name, 
                "indexes/scraped-tiles/", 
                data_dir / "indexes" / "scraped-tiles", 
                campaign_name, 
                aws_config
            )
        except Exception as e:
            console.print(f"[yellow]Warning: Auto-sync failed: {e}. Proceeding with local state.[/yellow]")

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[red]Campaign directory not found for {campaign_name}.[/red]")
        raise typer.Exit(1)
        
    from cocli.core.config import get_scraped_tiles_index_dir
    target_index_dir = campaign_dir / "indexes" / "target-tiles"
    global_scraped_dir = get_scraped_tiles_index_dir()

    if not target_index_dir.exists():
        console.print(f"[red]Target Index not found at {target_index_dir}. Run 'build-mission-index' first.[/red]")
        raise typer.Exit(1)

    # 1. Find all target tiles
    console.print(f"Scanning target index: {target_index_dir}...")
    target_files = list(target_index_dir.glob("**/*.csv"))
    console.print(f"Found {len(target_files)} total targets.")

    # 2. Filter for pending (Set Difference)
    pending_tasks: List[Dict[str, Any]] = []
    for tf in target_files:
        # Relative path is lat/lon/phrase.csv
        rel_path = tf.relative_to(target_index_dir)
        witness_path = global_scraped_dir / rel_path
        
        if not witness_path.exists():
            # Extract metadata from target file
            try:
                with open(tf, "r") as f:
                    reader = csv.DictReader(f)
                    row = next(reader)
                
                # phrase is the filename stem
                phrase_slug = str(tf.stem)
                tile_id = f"{rel_path.parent.parent.name}_{rel_path.parent.name}"
                
                pending_tasks.append({
                    "tile_id": tile_id,
                    "search_phrase": phrase_slug,
                    "latitude": float(row["latitude"]),
                    "longitude": float(row["longitude"])
                })
            except Exception as e:
                console.print(f"[red]Error reading {tf}: {e}[/red]")
        
        if len(pending_tasks) >= limit:
            break

    if not pending_tasks:
        console.print("[bold green]All targets in the mission index have been scraped![/bold green]")
        return

    console.print(f"[bold]Dispatching {len(pending_tasks)} pending tasks...[/bold]")

    if dry_run:
        console.print(f"[blue]Dry Run: Would queue {len(pending_tasks)} tasks.[/blue]")
        for t in pending_tasks:
             console.print(f"  - {t['search_phrase']} @ {t['tile_id']}")
        return

    queue_manager = get_queue_manager("scrape_tasks", use_cloud=True, queue_type="scrape")
    for t in pending_tasks:
        queue_manager.push(ScrapeTask(
            latitude=t["latitude"],
            longitude=t["longitude"],
            zoom=13,
            search_phrase=t["search_phrase"], # Note: this will be re-slugified by the task, which is fine
            campaign_name=campaign_name,
            tile_id=t["tile_id"],
            ack_token=None
        ))
    
    console.print(f"[bold green]Successfully queued {len(pending_tasks)} tasks.[/bold green]")
    console.print("[dim]Note: This command is now idempotent. No offset is needed.[/dim]")

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