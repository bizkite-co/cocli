import typer
import asyncio
import logging
from rich.console import Console
from playwright.async_api import async_playwright

from ..core.queue.factory import get_queue_manager
from ..scrapers.google_maps import scrape_google_maps
from ..models.queue import QueueMessage

logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer(no_args_is_help=True)

async def run_worker(headless: bool, debug: bool) -> None:
    try:
        scrape_queue = get_queue_manager("scrape_tasks", use_cloud=True, queue_type="scrape")
        enrichment_queue = get_queue_manager("enrichment", use_cloud=True, queue_type="enrichment")
    except ValueError as e:
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
            console.print(f"[cyan]Received Task:[/cyan] {task.search_phrase} @ {task.latitude}, {task.longitude}")
            
            try:
                # Construct location param
                location_param = {
                    "latitude": str(task.latitude),
                    "longitude": str(task.longitude)
                }
                
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
                    # We rely on default behavior or pass explicit options if needed
                    # For "Scout" mode, we might want to limit panning, but let's use default for now.
                ):
                    prospect_count += 1
                    
                    # Push to Enrichment Queue
                    # We check if it has a domain to enrich
                    if prospect.Domain and prospect.Name:
                        msg = QueueMessage(
                            domain=prospect.Domain,
                            company_slug="", # We might not have this yet? Or we generate it? 
                                             # Usually import_prospect generates it. 
                                             # For distributed, we might send "raw" data or just domain.
                                             # QueueMessage expects company_slug.
                            campaign_name=task.campaign_name,
                            force_refresh=task.force_refresh,
                            ack_token=None
                        )
                        # We need a slug. 
                        # Ideally, we should "Import" locally on the worker? No, worker is dumb.
                        # Maybe we just use slugify(domain)?
                        from ..core.text_utils import slugify
                        msg.company_slug = slugify(prospect.Name) # Approximation
                        
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
