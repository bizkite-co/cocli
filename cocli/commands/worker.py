import typer
import asyncio
import logging
import boto3
import csv # Added for details worker to read CSV
from datetime import datetime # Added for updated_at
from rich.console import Console
from playwright.async_api import async_playwright

from cocli.core.logging_config import setup_file_logging
from cocli.core.queue.factory import get_queue_manager
from cocli.scrapers.google_maps import scrape_google_maps
from cocli.scrapers.google_maps_details import scrape_google_maps_details
from cocli.models.scrape_task import GmItemTask
from cocli.models.google_maps_prospect import GoogleMapsProspect
from cocli.models.queue import QueueMessage
from cocli.core.prospects_csv_manager import ProspectsIndexManager
from cocli.core.text_utils import slugify

logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer(no_args_is_help=True)

import toml
import os
from pathlib import Path
from cocli.core.config import get_campaign, load_campaign_config, get_campaign_dir

logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer(no_args_is_help=True)

def ensure_campaign_config(campaign_name: str) -> None:
    """
    Ensures the campaign config exists locally. 
    If missing, attempts to fetch it from the campaign's web assets bucket.
    """
    campaign_dir = get_campaign_dir(campaign_name)
    config_path = campaign_dir / "config.toml"
    
    if config_path.exists():
        return

    console.print(f"[yellow]Local config for '{campaign_name}' not found. Attempting to fetch from S3...[/yellow]")
    
    # Deriving bucket name - following the convention in web.py
    # We don't have the domain slug yet because we don't have the config! 
    # This is a bit of a catch-22 if the bucket name is highly variable.
    # However, for now we'll assume the convention cocli-data-{campaign_name} 
    # or look for a standardized 'bootstrap' bucket if needed.
    # Given the user's setup, cocli-data-{campaign_name} is the data bucket.
    
    bucket_name = f"cocli-data-{campaign_name}"
    config_key = f"config.toml" # In the data bucket it might be at root or campaigns/{name}/config.toml
    
    # Try multiple common locations
    keys_to_try = [f"config.toml", f"campaigns/{campaign_name}/config.toml"]
    
    s3 = boto3.client("s3")
    for key in keys_to_try:
        try:
            console.print(f"  Trying s3://{bucket_name}/{key}...")
            campaign_dir.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket_name, key, str(config_path))
            console.print(f"[green]Successfully fetched config from S3.[/green]")
            return
        except Exception:
            continue
            
    console.print(f"[bold red]Failed to fetch config for '{campaign_name}' from S3 bucket '{bucket_name}'.[/bold red]")
    console.print(f"[dim]Note: Ensure 'web deploy' has been run for this campaign or the config is manually placed at {config_path}[/dim]")

async def run_worker(headless: bool, debug: bool, campaign_name: str) -> None:
    try:
        ensure_campaign_config(campaign_name)
        # S3_BUCKET following convention: cocli-data-{campaign}
        bucket_name = f"cocli-data-{campaign_name}"
        
        scrape_queue = get_queue_manager("scrape_tasks", use_cloud=True, queue_type="scrape", campaign_name=campaign_name)
        gm_list_item_queue = get_queue_manager("gm_list_item", use_cloud=True, queue_type="gm_list_item", campaign_name=campaign_name)
        
        # Determine AWS profile for S3 client
        config = load_campaign_config(campaign_name)
        aws_config = config.get("aws", {})
        profile_name = aws_config.get("profile") or aws_config.get("aws_profile")
        
        if profile_name:
            session = boto3.Session(profile_name=profile_name)
        else:
            session = boto3.Session()
        s3_client = session.client("s3")
        
    except Exception as e:
        console.print(f"[bold red]Configuration Error: {e}[/bold red]")
        return

    console.print(f"[bold blue]Worker started for campaign '{campaign_name}'. Polling for scrape tasks...[/bold blue]")

    async with async_playwright() as p:
        while True:  # Browser Restart Loop
            console.print("[blue]Launching browser...[/blue]")
            browser = None
            try:
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

                while True:  # Task Processing Loop
                    if not browser.is_connected():
                        console.print("[bold red]Browser is disconnected. Breaking task loop to restart.[/bold red]")
                        break

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
                        
                        # Watchdog: Enforce 15-minute timeout per task to prevent hangs
                        async with asyncio.timeout(900):
                            async for prospect in scrape_google_maps(
                                browser=browser,
                                location_param=location_param,
                                search_strings=[task.search_phrase],
                                campaign_name=task.campaign_name,
                                debug=debug,
                                force_refresh=task.force_refresh,
                                ttl_days=task.ttl_days,
                                grid_tiles=grid_tiles,
                                s3_client=s3_client,
                                s3_bucket=bucket_name
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
                                                s3_client.upload_file(str(file_path), bucket_name, s3_key)
                                            except Exception as e:
                                                console.print(f"[red]S3 Upload Error:[/red] {e}")

                                        # 3. Push to Details Queue
                                        details_task = GmItemTask(
                                            place_id=prospect.Place_ID,
                                            campaign_name=task.campaign_name,
                                            force_refresh=task.force_refresh,
                                            ack_token=None
                                        )
                                        gm_list_item_queue.push(details_task)
                        
                        console.print(f"[green]Task Complete. Found {prospect_count} prospects.[/green]")
                        scrape_queue.ack(task)
                        
                    except Exception as e:
                        console.print(f"[bold red]Task Failed: {e}[/bold red]")
                        scrape_queue.nack(task)
                        
                        # Critical: If the error suggests browser death, break the loop
                        if "Target page, context or browser has been closed" in str(e) or not browser.is_connected():
                             console.print("[red]Browser fatal error detected.[/red]")
                             break

            except Exception as e:
                console.print(f"[bold red]Worker Error: {e}[/bold red]")
            
            finally:
                if browser:
                    try:
                        await browser.close()
                    except Exception:
                        pass
                console.print("[yellow]Restarting browser session in 5 seconds...[/yellow]")
                await asyncio.sleep(5)

async def run_details_worker(headless: bool, debug: bool, campaign_name: str) -> None:
    try:
        ensure_campaign_config(campaign_name)
        bucket_name = f"cocli-data-{campaign_name}"

        gm_list_item_queue = get_queue_manager("gm_list_item", use_cloud=True, queue_type="gm_list_item", campaign_name=campaign_name)
        enrichment_queue = get_queue_manager("enrichment", use_cloud=True, queue_type="enrichment", campaign_name=campaign_name)
        
        # Determine AWS profile for S3 client
        config = load_campaign_config(campaign_name)
        aws_config = config.get("aws", {})
        profile_name = aws_config.get("profile") or aws_config.get("aws_profile")
        
        if profile_name:
            session = boto3.Session(profile_name=profile_name)
        else:
            session = boto3.Session()
        s3_client = session.client("s3")
        
    except Exception as e:
        console.print(f"[bold red]Configuration Error: {e}[/bold red]")
        return

    console.print(f"[bold blue]Details Worker started for campaign '{campaign_name}'. Polling for detail tasks...[/bold blue]")

    async with async_playwright() as p:
        while True: # Browser Restart Loop
            console.print("[blue]Launching browser...[/blue]")
            browser = None
            try:
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
            
                while True: # Task Loop
                    if not browser.is_connected():
                        console.print("[bold red]Browser is disconnected. Restarting.[/bold red]")
                        break

                    tasks = gm_list_item_queue.poll(batch_size=1)
                    
                    if not tasks:
                        await asyncio.sleep(5)
                        continue
                    
                    task = tasks[0] # batch_size=1
                    console.print(f"[cyan]Detail Task:[/cyan] {task.place_id}")
                    
                    try:
                        csv_manager = ProspectsIndexManager(task.campaign_name)
                        
                        # 1. Scrape Details
                        # Use new playwright page to not interfere with other potential browser operations
                        page = await browser.new_page()
                        try:
                            detailed_prospect_data = await scrape_google_maps_details(
                                page=page,
                                place_id=task.place_id,
                                campaign_name=task.campaign_name,
                                debug=debug
                            )
                        finally:
                            await page.close()
                        
                        if not detailed_prospect_data:
                            console.print(f"[yellow]No details scraped for {task.place_id}. Nacking task.[/yellow]")
                            gm_list_item_queue.nack(task)
                            continue

                        # 2. Load existing prospect data (if any) and merge
                        existing_prospect = None
                        file_path = csv_manager.get_file_path(task.place_id) # This will get it from inbox/ or root/
                        if file_path.exists():
                            with open(file_path, 'r', encoding='utf-8') as f:
                                reader = csv.DictReader(f)
                                existing_data = next(reader, None)
                                if existing_data:
                                    # Use model_validate to handle type conversions from strings
                                    existing_prospect = GoogleMapsProspect.model_validate(existing_data) 
                        
                        final_prospect_data = detailed_prospect_data
                        if existing_prospect:
                            # Merge existing with new details, new details take precedence
                            merged_data = existing_prospect.model_dump()
                            # Use exclude_unset=True to ensure only explicitly set fields in detailed_prospect_data update merged_data
                            merged_data.update(detailed_prospect_data.model_dump(exclude_unset=True)) 
                            final_prospect_data = GoogleMapsProspect.model_validate(merged_data)
                        
                        # Update 'updated_at'
                        final_prospect_data.updated_at = datetime.now()

                        # 3. Save updated prospect to Local Index
                        if csv_manager.append_prospect(final_prospect_data):
                            # 4. Upload to S3 (Immediate Sync)
                            s3_key = f"campaigns/{task.campaign_name}/indexes/google_maps_prospects/{file_path.name}"
                            try:
                                s3_client.upload_file(str(file_path), bucket_name, s3_key)
                                console.print(f"[green]Updated and uploaded {file_path.name} to S3.[/green]")
                            except Exception as e:
                                console.print(f"[red]S3 Upload Error:[/red] {e}")

                        # 5. Push to Enrichment Queue
                        if final_prospect_data.Domain and final_prospect_data.Name:
                            msg = QueueMessage(
                                domain=final_prospect_data.Domain,
                                company_slug=slugify(final_prospect_data.Name),
                                campaign_name=task.campaign_name,
                                force_refresh=task.force_refresh,
                                ack_token=None
                            )
                            enrichment_queue.push(msg)
                            console.print(f"[cyan]Pushed {final_prospect_data.Domain} to Enrichment Queue[/cyan]")
                        
                        console.print(f"[green]Detailing Complete for {task.place_id}.[/green]")
                        gm_list_item_queue.ack(task)
                        
                    except Exception as e:
                        console.print(f"[bold red]Detail Task Failed for {task.place_id}: {e}[/bold red]")
                        gm_list_item_queue.nack(task)

                        # Critical: If the error suggests browser death, break the loop
                        if "Target page, context or browser has been closed" in str(e) or not browser.is_connected():
                             console.print("[red]Browser fatal error detected.[/red]")
                             break
            
            except Exception as e:
                console.print(f"[bold red]Worker Error: {e}[/bold red]")
            
            finally:
                if browser:
                    try:
                        await browser.close()
                    except Exception:
                        pass
                console.print("[yellow]Restarting browser session in 5 seconds...[/yellow]")
                await asyncio.sleep(5)

@app.command()
def scrape(
    campaign: str = typer.Option(None, "--campaign", "-c", help="Campaign name."),
    headed: bool = typer.Option(False, "--headed", help="Run browser in headed mode."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging.")
) -> None:
    """
    Starts a worker node that polls for scrape tasks and executes them.
    """
    if not campaign:
        campaign = get_campaign()
    if not campaign:
        console.print("[bold red]Error: No campaign specified and no active context.[/bold red]")
        raise typer.Exit(1)

    log_level = logging.DEBUG if debug else logging.INFO
    setup_file_logging("worker_scrape", console_level=log_level)
    asyncio.run(run_worker(not headed, debug, campaign))

@app.command()
def details(
    campaign: str = typer.Option(None, "--campaign", "-c", help="Campaign name."),
    headed: bool = typer.Option(False, "--headed", help="Run browser in headed mode."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging.")
) -> None:
    """
    Starts a worker node that polls for details tasks (Place IDs) and scrapes them.
    """
    if not campaign:
        campaign = get_campaign()
    if not campaign:
        console.print("[bold red]Error: No campaign specified and no active context.[/bold red]")
        raise typer.Exit(1)

    log_level = logging.DEBUG if debug else logging.INFO
    setup_file_logging("worker_details", console_level=log_level)
    asyncio.run(run_details_worker(not headed, debug, campaign))

if __name__ == "__main__":
    app()