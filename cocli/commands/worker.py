import typer
import asyncio
import logging
import boto3
from rich.console import Console
from playwright.async_api import async_playwright

from ..core.queue.factory import get_queue_manager
from ..scrapers.google_maps import scrape_google_maps
from ..models.queue import QueueMessage
from ..core.prospects_csv_manager import ProspectsIndexManager
from ..core.text_utils import slugify

logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer(no_args_is_help=True)

# Hardcoded bucket for now, or move to config/env
S3_BUCKET = "cocli-data-turboship"

async def run_worker(headless: bool, debug: bool) -> None:
    try:
        scrape_queue = get_queue_manager("scrape_tasks", use_cloud=True, queue_type="scrape")
        enrichment_queue = get_queue_manager("enrichment", use_cloud=True, queue_type="enrichment")
        s3_client = boto3.client("s3")
    except Exception as e:
        console.print(f"[bold red]Configuration Error: {e}[/bold red]")
        return

    console.print("[bold blue]Worker started. Polling for scrape tasks...[/bold blue]")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--disable-gpu'
            ]
        )
        
        while True:
            tasks = scrape_queue.poll(batch_size=1)
            
            if not tasks:
                await asyncio.sleep(5)
                continue
            
            task = tasks[0] # batch_size=1
            
            # Identify Mode
            grid_tiles = None
            if task.tile_id:
                console.print(f"[cyan]Grid Task ({task.tile_id}):[/cyan] {task.search_phrase}")
                grid_tiles = [{
                    "id": task.tile_id,
                    "center_lat": task.latitude,
                    "center_lon": task.longitude,
                    # Fallback center dict for strategy compatibility
                    "center": {"lat": task.latitude, "lon": task.longitude}
                }]
            else:
                console.print(f"[cyan]Point Task:[/cyan] {task.search_phrase} @ {task.latitude}, {task.longitude}")
            
            try:
                # Construct location param
                location_param = {
                    "latitude": str(task.latitude),
                    "longitude": str(task.longitude)
                }
                
                # Use manager for this campaign
                csv_manager = ProspectsIndexManager(task.campaign_name)
                
                # Execute Scrape
                # Note: scrape_google_maps is an async generator
                prospect_count = 0
                async for prospect in scrape_google_maps(
                    browser=browser,
                    location_param=location_param,
                    search_strings=[task.search_phrase],
                    campaign_name=task.campaign_name,
                    debug=debug,
                    force_refresh=task.force_refresh,
                    ttl_days=task.ttl_days,
                    grid_tiles=grid_tiles
                ):
                    prospect_count += 1
                    
                    # 1. Save to Local Index (Worker's disk)
                    if csv_manager.append_prospect(prospect):
                        # 2. Upload to S3 (Immediate Sync)
                        if prospect.Place_ID:
                            file_path = csv_manager.get_file_path(prospect.Place_ID)
                            if file_path.exists():
                                # Construct S3 Key: campaigns/{campaign}/indexes/google_maps_prospects/{Place_ID}.csv
                                s3_key = f"campaigns/{task.campaign_name}/indexes/google_maps_prospects/{file_path.name}"
                                try:
                                    s3_client.upload_file(str(file_path), S3_BUCKET, s3_key)
                                except Exception as e:
                                    console.print(f"[red]S3 Upload Error:[/red] {e}")

                    # 3. Push to Enrichment Queue
                    if prospect.Domain and prospect.Name:
                        msg = QueueMessage(
                            domain=prospect.Domain,
                            company_slug=slugify(prospect.Name),
                            campaign_name=task.campaign_name,
                            force_refresh=task.force_refresh,
                            ack_token=None
                        )
                        enrichment_queue.push(msg)
                
                console.print(f"[green]Task Complete. Found {prospect_count} prospects.[/green]")
                scrape_queue.ack(task)
                
            except Exception as e:
                console.print(f"[bold red]Task Failed: {e}[/bold red]")
                scrape_queue.nack(task)
                # Maybe restart browser if it crashed?

@app.command()
def scrape(
    headed: bool = typer.Option(False, "--headed", help="Run browser in headed mode."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging.")
) -> None:
    """
    Starts a worker node that polls for scrape tasks and executes them.
    """
    asyncio.run(run_worker(not headed, debug))

if __name__ == "__main__":
    app()
