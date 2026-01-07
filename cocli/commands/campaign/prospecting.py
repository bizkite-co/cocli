import typer
import asyncio
import logging
import toml
import json
import httpx
from typing import Optional, List, Dict, Any, cast
from rich.console import Console
from playwright.async_api import async_playwright
import yaml

from cocli.core.config import get_companies_dir, get_campaign_dir, get_campaign, get_enrichment_service_url
from cocli.core.importing import import_prospect
from cocli.core.prospects_csv_manager import ProspectsIndexManager
from cocli.core.scrape_index import ScrapeIndex
from cocli.core.location_prospects_index import LocationProspectsIndex
from cocli.core.queue.factory import get_queue_manager
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