import typer
import asyncio
import logging
import boto3 # type: ignore
import csv 
from datetime import datetime 
from pathlib import Path
from typing import Optional
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
from cocli.core.config import get_campaign, load_campaign_config, get_campaigns_dir

# Load Version
VERSION_FILE = Path(__file__).parent.parent.parent / "VERSION"
try:
    VERSION = VERSION_FILE.read_text().strip()
except Exception:
    VERSION = "unknown"

logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer(no_args_is_help=True)

def ensure_campaign_config(campaign_name: str) -> None:
    """
    Ensures the campaign config exists locally. 
    If missing, attempts to fetch it from the campaign's web assets bucket.
    """
    # Use get_campaigns_dir() / campaign_name instead of get_campaign_dir() 
    # because get_campaign_dir() returns None if the directory doesn't exist.
    campaign_dir = get_campaigns_dir() / campaign_name
    config_path = campaign_dir / "config.toml"
    
    if config_path.exists():
        logger.info(f"Found local config for '{campaign_name}'.")
        return

    logger.warning(f"Local config for '{campaign_name}' not found at {config_path}. Attempting to fetch from S3...")
    
    bucket_name = f"cocli-data-{campaign_name}"
    keys_to_try = ["config.toml", f"campaigns/{campaign_name}/config.toml"]
    
    s3 = boto3.client("s3")
    for key in keys_to_try:
        try:
            logger.info(f"Trying s3://{bucket_name}/{key}...")
            campaign_dir.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket_name, key, str(config_path))
            logger.info("Successfully fetched config from S3.")
            return
        except Exception:
            continue
            
    logger.error(f"Failed to fetch config for '{campaign_name}' from S3 bucket '{bucket_name}'.")

async def run_worker(headless: bool, debug: bool, campaign_name: str) -> None:
    try:
        ensure_campaign_config(campaign_name)
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
        logger.error(f"Configuration Error: {e}")
        return

    logger.info(f"Worker v{VERSION} started for campaign '{campaign_name}'. Polling for tasks...")

    async with async_playwright() as p:
        while True:  # Browser Restart Loop
            logger.info("Launching browser...")
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
                        logger.error("Browser is disconnected. Breaking task loop to restart.")
                        break

                    tasks = scrape_queue.poll(batch_size=1)
                    
                    if not tasks:
                        await asyncio.sleep(5)
                        continue
                    
                    task = tasks[0] # batch_size=1
                    
                    # Identify Mode
                    grid_tiles = None
                    if task.tile_id:
                        logger.info(f"Grid Task ({task.tile_id}): {task.search_phrase}")
                        grid_tiles = [{
                            "id": task.tile_id,
                            "center_lat": task.latitude,
                            "center_lon": task.longitude,
                            "center": {"lat": task.latitude, "lon": task.longitude}
                        }]
                    else:
                        logger.info(f"Point Task: {task.search_phrase} @ {task.latitude}, {task.longitude}")
                    
                    try:
                        location_param = {
                            "latitude": str(task.latitude),
                            "longitude": str(task.longitude)
                        }
                        csv_manager = ProspectsIndexManager(task.campaign_name)
                        prospect_count = 0
                        
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
                                if csv_manager.append_prospect(prospect):
                                    if prospect.Place_ID:
                                        file_path = csv_manager.get_file_path(prospect.Place_ID)
                                        if file_path.exists():
                                            s3_key = f"campaigns/{task.campaign_name}/indexes/google_maps_prospects/{file_path.name}"
                                            try:
                                                s3_client.upload_file(str(file_path), bucket_name, s3_key)
                                            except Exception as e:
                                                logger.error(f"S3 Upload Error: {e}")

                                        details_task = GmItemTask(
                                            place_id=prospect.Place_ID,
                                            campaign_name=task.campaign_name,
                                            force_refresh=task.force_refresh,
                                            ack_token=None
                                        )
                                        gm_list_item_queue.push(details_task)
                        
                        logger.info(f"Task Complete. Found {prospect_count} prospects.")
                        scrape_queue.ack(task)
                        
                    except Exception as e:
                        logger.error(f"Task Failed: {e}")
                        scrape_queue.nack(task)
                        if "Target page, context or browser has been closed" in str(e) or not browser.is_connected():
                             logger.critical("Browser fatal error detected.")
                             break

            except Exception as e:
                logger.error(f"Worker Error: {e}")
            
            finally:
                if browser:
                    try:
                        await browser.close()
                    except Exception:
                        pass
                logger.info("Restarting browser session in 5 seconds...")
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
        logger.error(f"Configuration Error: {e}")
        return

    logger.info(f"Details Worker v{VERSION} started for campaign '{campaign_name}'. Polling for tasks...")

    async with async_playwright() as p:
        while True: # Browser Restart Loop
            logger.info("Launching browser...")
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
                        logger.error("Browser is disconnected. Restarting.")
                        break

                    tasks = gm_list_item_queue.poll(batch_size=1)
                    if not tasks:
                        await asyncio.sleep(5)
                        continue
                    
                    task = tasks[0] # batch_size=1
                    logger.info(f"Detail Task: {task.place_id}")
                    
                    try:
                        csv_manager = ProspectsIndexManager(task.campaign_name)
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
                            logger.warning(f"No details scraped for {task.place_id}. Nacking task.")
                            gm_list_item_queue.nack(task)
                            continue

                        existing_prospect = None
                        file_path = csv_manager.get_file_path(task.place_id)
                        if file_path.exists():
                            with open(file_path, 'r', encoding='utf-8') as f:
                                reader = csv.DictReader(f)
                                existing_data = next(reader, None)
                                if existing_data:
                                    existing_prospect = GoogleMapsProspect.model_validate(existing_data) 
                        
                        final_prospect_data = detailed_prospect_data
                        if existing_prospect:
                            merged_data = existing_prospect.model_dump()
                            merged_data.update(detailed_prospect_data.model_dump(exclude_unset=True)) 
                            final_prospect_data = GoogleMapsProspect.model_validate(merged_data)
                        
                        final_prospect_data.updated_at = datetime.now()

                        if csv_manager.append_prospect(final_prospect_data):
                            s3_key = f"campaigns/{task.campaign_name}/indexes/google_maps_prospects/{file_path.name}"
                            try:
                                s3_client.upload_file(str(file_path), bucket_name, s3_key)
                                logger.info(f"Updated and uploaded {file_path.name} to S3.")
                            except Exception as e:
                                logger.error(f"S3 Upload Error: {e}")

                        if final_prospect_data.Domain and final_prospect_data.Name:
                            msg = QueueMessage(
                                domain=final_prospect_data.Domain,
                                company_slug=slugify(final_prospect_data.Name),
                                campaign_name=task.campaign_name,
                                force_refresh=task.force_refresh,
                                ack_token=None
                            )
                            enrichment_queue.push(msg)
                            logger.info(f"Pushed {final_prospect_data.Domain} to Enrichment Queue")
                        
                        logger.info(f"Detailing Complete for {task.place_id}.")
                        gm_list_item_queue.ack(task)
                        
                    except Exception as e:
                        logger.error(f"Detail Task Failed for {task.place_id}: {e}")
                        gm_list_item_queue.nack(task)
                        if "Target page, context or browser has been closed" in str(e) or not browser.is_connected():
                             logger.critical("Browser fatal error detected.")
                             break
            
            except Exception as e:
                logger.error(f"Worker Error: {e}")
            
            finally:
                if browser:
                    try:
                        await browser.close()
                    except Exception:
                        pass
                logger.info("Restarting browser session in 5 seconds...")
                await asyncio.sleep(5)

@app.command()
def scrape(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name."),
    headed: bool = typer.Option(False, "--headed", help="Run browser in headed mode."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging.")
) -> None:
    """
    Starts a worker node that polls for scrape tasks and executes them.
    """
    effective_campaign = campaign
    if not effective_campaign:
        effective_campaign = get_campaign()
    
    # We set up logging after we might know the campaign, but worker log files are generic
    log_level = logging.DEBUG if debug else logging.INFO
    setup_file_logging("worker_scrape", console_level=log_level)
    
    logger.info(f"Effective campaign: {effective_campaign}")
    
    if not effective_campaign:
        logger.error("No campaign specified and no active context.")
        raise typer.Exit(1)

    asyncio.run(run_worker(not headed, debug, effective_campaign))

@app.command()
def details(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name."),
    headed: bool = typer.Option(False, "--headed", help="Run browser in headed mode."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging.")
) -> None:
    """
    Starts a worker node that polls for details tasks (Place IDs) and scrapes them.
    """
    effective_campaign = campaign
    if not effective_campaign:
        effective_campaign = get_campaign()
        
    log_level = logging.DEBUG if debug else logging.INFO
    setup_file_logging("worker_details", console_level=log_level)

    logger.info(f"Effective campaign: {effective_campaign}")

    if not effective_campaign:
        logger.error("No campaign specified and no active context.")
        raise typer.Exit(1)

    asyncio.run(run_details_worker(not headed, debug, effective_campaign))