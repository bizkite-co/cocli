import typer
import asyncio
import logging
import os
import boto3
import csv 
import socket
from datetime import datetime 
from pathlib import Path
from typing import Optional, Any
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
from cocli.utils.playwright_utils import setup_optimized_context

# Load Version
def get_version() -> str:
    # 1. Try file in project root (dev mode)
    try:
        root_version = (Path(__file__).parent.parent.parent / "VERSION")
        if root_version.exists():
            return root_version.read_text().strip()
    except Exception:
        pass
    
    # 2. Try file in package dir (installed mode)
    try:
        pkg_version = (Path(__file__).parent.parent / "VERSION")
        if pkg_version.exists():
            return pkg_version.read_text().strip()
    except Exception:
        pass
        
    # 3. Fallback to importlib.metadata
    try:
        from importlib.metadata import version
        return version("cocli")
    except Exception:
        pass
        
    return "unknown"

VERSION = get_version()

logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer(no_args_is_help=True)

def ensure_campaign_config(campaign_name: str) -> None:
    """
    Ensures the campaign config exists locally. 
    If missing, attempts to fetch it from the campaign's data bucket.
    """
    # Use get_campaigns_dir() / campaign_name instead of get_campaign_dir() 
    # because get_campaign_dir() returns None if the directory doesn't exist.
    campaign_dir = get_campaigns_dir() / campaign_name
    config_path = campaign_dir / "config.toml"
    
    if config_path.exists():
        logger.info(f"Found local config for '{campaign_name}'.")
        return

    logger.warning(f"Local config for '{campaign_name}' not found at {config_path}. Attempting to fetch from S3...")
    
    # Determine AWS profile for initial bootstrap
    profile_name = os.getenv("AWS_PROFILE")
    if profile_name:
        session = boto3.Session(profile_name=profile_name)
    else:
        session = boto3.Session()
    s3 = session.client("s3")

    # Try to determine the bucket name without the config file
    # Default fallback
    bucket_name = f"cocli-data-{campaign_name}"
    
    # Check if we are running in a context where we can guess the bucket better
    # or if we should try a few common patterns.
    # For roadmap, it is roadmap-cocli-data-use1
    potential_buckets = [bucket_name, f"{campaign_name}-cocli-data-use1"]
    
    keys_to_try = ["config.toml", f"campaigns/{campaign_name}/config.toml"]
    
    for b in potential_buckets:
        for key in keys_to_try:
            try:
                logger.info(f"Trying s3://{b}/{key}...")
                campaign_dir.mkdir(parents=True, exist_ok=True)
                s3.download_file(b, key, str(config_path))
                logger.info(f"Successfully fetched config from S3 to {config_path}")
                return
            except Exception as e:
                logger.debug(f"Failed to fetch s3://{b}/{key}: {e}")
                continue
            
    logger.error(f"Failed to fetch config for '{campaign_name}' from S3.")

async def run_worker(headless: bool, debug: bool, campaign_name: str, workers: int = 1) -> None:
    try:
        ensure_campaign_config(campaign_name)
        
        # Determine AWS profile for S3 client
        config = load_campaign_config(campaign_name)
        aws_config = config.get("aws", {})
        bucket_name = aws_config.get("cocli_data_bucket_name") or f"cocli-data-{campaign_name}"
        
        if os.getenv("COCLI_RUNNING_IN_FARGATE"):
            profile_name = None
        else:
            profile_name = aws_config.get("profile") or aws_config.get("aws_profile")
        
        if profile_name:
            session = boto3.Session(profile_name=profile_name)
        else:
            session = boto3.Session()
        s3_client = session.client("s3")

        scrape_queue = get_queue_manager("scrape_tasks", use_cloud=True, queue_type="scrape", campaign_name=campaign_name)
        gm_list_item_queue = get_queue_manager("gm_list_item", use_cloud=True, queue_type="gm_list_item", campaign_name=campaign_name)
        
    except Exception as e:
        logger.error(f"Configuration Error: {e}")
        return

    logger.info(f"Worker v{VERSION} started for campaign '{campaign_name}' with {workers} worker(s). Polling for tasks...")

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

                tasks = [
                    _run_scrape_task_loop(browser, scrape_queue, gm_list_item_queue, s3_client, bucket_name, debug)
                    for _ in range(workers)
                ]
                await asyncio.gather(*tasks)

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

async def _run_scrape_task_loop(browser: Any, scrape_queue: Any, gm_list_item_queue: Any, s3_client: Any, bucket_name: str, debug: bool) -> None:
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

async def run_details_worker(headless: bool, debug: bool, campaign_name: str, once: bool = False, processed_by: Optional[str] = None, browser: Optional[Any] = None, workers: int = 1) -> None:
    if not processed_by:
        processed_by = f"local-worker-{socket.gethostname()}"
    try:
        ensure_campaign_config(campaign_name)
        
        # Determine AWS profile for S3 client
        config = load_campaign_config(campaign_name)
        aws_config = config.get("aws", {})
        bucket_name = aws_config.get("cocli_data_bucket_name") or f"cocli-data-{campaign_name}"
        
        if os.getenv("COCLI_RUNNING_IN_FARGATE"):
            profile_name = None
        else:
            profile_name = aws_config.get("profile") or aws_config.get("aws_profile")
        
        if profile_name:
            session = boto3.Session(profile_name=profile_name)
        else:
            session = boto3.Session()
        s3_client = session.client("s3")

        gm_list_item_queue = get_queue_manager("gm_list_item", use_cloud=True, queue_type="gm_list_item", campaign_name=campaign_name)
        enrichment_queue = get_queue_manager("enrichment", use_cloud=True, queue_type="enrichment", campaign_name=campaign_name)
        
        if hasattr(gm_list_item_queue, 'queue_url'):
             logger.info(f"run_details_worker: Using GM List Item Queue URL: {gm_list_item_queue.queue_url}")
        
    except Exception as e:
        logger.error(f"Configuration Error: {e}")
        return

    logger.info(f"Details Worker v{VERSION} started for campaign '{campaign_name}' with {workers} worker(s). Polling for tasks...")

    if browser:
        # We need a context to setup the tracker
        # For simplicity in the provided browser case, we'll skip optimization
        # unless we want to refactor the caller to provide a context.
        tasks = [
            _run_details_task_loop(browser, gm_list_item_queue, enrichment_queue, s3_client, bucket_name, debug, once, processed_by)
            for _ in range(workers)
        ]
        await asyncio.gather(*tasks)
    else:
        async with async_playwright() as p:
            while True: # Browser Restart Loop
                logger.info("Launching browser...")
                browser_instance = None
                try:
                    browser_instance = await p.chromium.launch(
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
                    
                    # Create context and setup optimizations
                    context = await browser_instance.new_context()
                    tracker = await setup_optimized_context(context)
                    
                    tasks = [
                        _run_details_task_loop(context, gm_list_item_queue, enrichment_queue, s3_client, bucket_name, debug, once, processed_by, tracker=tracker)
                        for _ in range(workers)
                    ]
                    await asyncio.gather(*tasks)
                    if once:
                        break
                
                except Exception as e:
                    logger.error(f"Worker Error: {e}")
                
                finally:
                    if browser_instance:
                        try:
                            await browser_instance.close()
                        except Exception:
                            pass
                    if once:
                        break
                    logger.info("Restarting browser session in 5 seconds...")
                    await asyncio.sleep(5)

async def _run_details_task_loop(browser_or_context: Any, gm_list_item_queue: Any, enrichment_queue: Any, s3_client: Any, bucket_name: str, debug: bool, once: bool, processed_by: str, tracker: Optional[Any] = None) -> None:
    while True: # Task Loop
        # BrowserContext doesn't have is_connected, check the browser if possible
        connected = True
        if hasattr(browser_or_context, 'is_connected'):
            connected = browser_or_context.is_connected()
        elif hasattr(browser_or_context, 'browser') and browser_or_context.browser:
            connected = browser_or_context.browser.is_connected()

        if not connected:
            logger.error("Browser is disconnected. Restarting.")
            break

        tasks = gm_list_item_queue.poll(batch_size=1)
        if not tasks:
            if once:
                logger.info("run_details_worker(once=True): No tasks found in GM List Item queue.")
                return # Exit if in single-run mode and queue empty
            await asyncio.sleep(5)
            continue
        
        task = tasks[0] # batch_size=1
        logger.info(f"Detail Task found: {task.place_id}")
        
        start_mb = 0.0
        if tracker:
            start_mb = tracker.get_mb()
        
        try:
            csv_manager = ProspectsIndexManager(task.campaign_name)
            file_path = csv_manager.get_file_path(task.place_id)
            s3_key = f"campaigns/{task.campaign_name}/indexes/google_maps_prospects/{file_path.name}"
            
            # 1. Try to fetch existing data from S3 first (if not local)
            if not file_path.exists():
                try:
                    s3_client.download_file(bucket_name, s3_key, str(file_path))
                    logger.debug(f"Fetched existing data for {task.place_id} from S3.")
                except Exception:
                    # Not found on S3 is fine, it's a new lead
                    pass

            existing_prospect = None
            if file_path.exists():
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        existing_data = next(reader, None)
                        if existing_data:
                            existing_prospect = GoogleMapsProspect.model_validate(existing_data) 
                except Exception as e:
                    logger.warning(f"Error reading local file {file_path}: {e}")

            # 2. Check freshness
            if existing_prospect and not task.force_refresh:
                if existing_prospect.updated_at:
                    # Convert updated_at if it's a string (from CSV)
                    u_at = existing_prospect.updated_at
                    if isinstance(u_at, str):
                        try:
                            u_at = datetime.fromisoformat(u_at)
                        except ValueError:
                            u_at = None
                    
                    if u_at:
                        # Ensure u_at is naive for comparison
                        if u_at.tzinfo is not None:
                            u_at = u_at.replace(tzinfo=None)
                        
                        age_seconds = (datetime.now() - u_at).total_seconds()
                        age_days = age_seconds / 86400
                        
                        if age_days < 30:
                            logger.info(f"Skipping scrape for {task.place_id}. Data is fresh ({max(0, int(age_days))} days old).")
                            
                            # Ensure it's in the enrichment queue if it has a domain
                            if existing_prospect.Domain and existing_prospect.Name:
                                msg = QueueMessage(
                                    domain=existing_prospect.Domain,
                                    company_slug=slugify(existing_prospect.Name),
                                    campaign_name=task.campaign_name,
                                    force_refresh=task.force_refresh,
                                    ack_token=None
                                )
                                enrichment_queue.push(msg)
                            
                            gm_list_item_queue.ack(task)
                            if once:
                                return
                            continue

            # 3. Proceed with Scrape
            page = await browser_or_context.new_page()
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
                if once:
                    return
                continue
            
            detailed_prospect_data.processed_by = processed_by

            # Merge with existing data if we have it
            final_prospect_data = detailed_prospect_data
            if existing_prospect:
                merged_data = existing_prospect.model_dump()
                # Update with new data, but keep old data where new is missing
                new_data = detailed_prospect_data.model_dump(exclude_unset=True)
                merged_data.update({k: v for k, v in new_data.items() if v is not None}) 
                final_prospect_data = GoogleMapsProspect.model_validate(merged_data)
            
            final_prospect_data.updated_at = datetime.now()

            if csv_manager.append_prospect(final_prospect_data):
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
            
            # --- Email Indexing ---
            # If the GMB details scrape found an email, index it immediately
            # Note: GMB Parser doesn't always find emails, but if it does, we want it.
            if hasattr(final_prospect_data, 'Email') and final_prospect_data.Email:
                try:
                    from cocli.core.email_index_manager import EmailIndexManager
                    from cocli.models.email import EmailEntry
                    
                    email_manager = EmailIndexManager(task.campaign_name)
                    entry = EmailEntry(
                        email=final_prospect_data.Email,
                        domain=final_prospect_data.Domain or final_prospect_data.Email.split('@')[-1],
                        company_slug=final_prospect_data.company_slug,
                        source="gmb_details_worker",
                        tags=[task.campaign_name]
                    )
                    email_manager.add_email(entry)
                    logger.info(f"Indexed email from GMB details: {final_prospect_data.Email}")
                except Exception as e:
                    logger.warning(f"Failed to index email from GMB details: {e}")
            # ----------------------

            end_mb = 0.0
            if tracker:
                end_mb = tracker.get_mb()
                logger.info(f"Detailing Complete for {task.place_id}. Bandwidth: {end_mb - start_mb:.2f} MB")
            else:
                logger.info(f"Detailing Complete for {task.place_id}.")
            
            gm_list_item_queue.ack(task)
            
            if once:
                return # Success - return to main loop

        except Exception as e:
            logger.error(f"Detail Task Failed for {task.place_id}: {e}")
            gm_list_item_queue.nack(task)
            if once:
                return
            
            connected = True
            if hasattr(browser_or_context, 'is_connected'):
                connected = browser_or_context.is_connected()
            elif hasattr(browser_or_context, 'browser') and browser_or_context.browser:
                connected = browser_or_context.browser.is_connected()

            if "Target page, context or browser has been closed" in str(e) or not connected:
                 logger.critical("Browser fatal error detected.")
                 break

@app.command()
def supervisor(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name."),
    headed: bool = typer.Option(False, "--headed", help="Run browser in headed mode."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging."),
    interval: int = typer.Option(60, "--interval", help="Seconds between config checks.")
) -> None:
    """
    Starts a supervisor that dynamically manages scrape and details workers based on config.
    """
    effective_campaign = campaign
    if not effective_campaign:
        effective_campaign = os.getenv("CAMPAIGN_NAME")
    if not effective_campaign:
        effective_campaign = get_campaign()

    if not effective_campaign:
        logger.error("No campaign specified and no active context.")
        raise typer.Exit(1)

    log_level = logging.DEBUG if debug else logging.INFO
    setup_file_logging("supervisor", console_level=log_level)

    asyncio.run(run_supervisor(not headed, debug, effective_campaign, interval))

def sync_campaign_config(campaign_name: str) -> None:
    """
    Forcefully fetches the latest config.toml from S3.
    """
    campaign_dir = get_campaigns_dir() / campaign_name
    config_path = campaign_dir / "config.toml"
    
    # Determine AWS profile for initial bootstrap
    profile_name = os.getenv("AWS_PROFILE")
    if profile_name:
        session = boto3.Session(profile_name=profile_name)
    else:
        session = boto3.Session()
    s3 = session.client("s3")

    # Bucket patterns
    bucket_name = f"cocli-data-{campaign_name}"
    potential_buckets = [bucket_name, f"{campaign_name}-cocli-data-use1"]
    keys_to_try = ["config.toml", f"campaigns/{campaign_name}/config.toml"]
    
    for b in potential_buckets:
        for key in keys_to_try:
            try:
                logger.debug(f"Syncing s3://{b}/{key}...")
                s3.download_file(b, key, str(config_path))
                logger.debug("Synced config from S3.")
                return
            except Exception:
                continue

async def run_supervisor(headless: bool, debug: bool, campaign_name: str, interval: int) -> None:
    hostname = socket.gethostname().split('.')[0]
    logger.info(f"Supervisor started on host '{hostname}' for campaign '{campaign_name}'.")

    # Shared browser instance for all tasks on this host
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

        scrape_tasks: dict[int, asyncio.Task[Any]] = {}
        details_tasks: dict[int, asyncio.Task[Any]] = {}

        # Setup queues and clients once
        try:
            ensure_campaign_config(campaign_name)
            config = load_campaign_config(campaign_name)
            aws_config = config.get("aws", {})
            bucket_name = aws_config.get("cocli_data_bucket_name") or f"cocli-data-{campaign_name}"
            
            if os.getenv("COCLI_RUNNING_IN_FARGATE"):
                profile_name = None
            else:
                profile_name = aws_config.get("profile") or aws_config.get("aws_profile")
            
            if profile_name:
                session = boto3.Session(profile_name=profile_name)
            else:
                session = boto3.Session()
            s3_client = session.client("s3")

            scrape_queue = get_queue_manager("scrape_tasks", use_cloud=True, queue_type="scrape", campaign_name=campaign_name)
            gm_list_item_queue = get_queue_manager("gm_list_item", use_cloud=True, queue_type="gm_list_item", campaign_name=campaign_name)
            enrichment_queue = get_queue_manager("enrichment", use_cloud=True, queue_type="enrichment", campaign_name=campaign_name)
            
            processed_by = f"supervisor-{hostname}"
        except Exception as e:
            logger.error(f"Supervisor initialization failed: {e}")
            await browser.close()
            return

        while True:
            try:
                # 0. Sync config from S3
                sync_campaign_config(campaign_name)

                # 1. Reload Config (from local file, which should be synced from S3)
                config = load_campaign_config(campaign_name)
                prospecting = config.get("prospecting", {})
                scaling = prospecting.get("scaling", {}).get(hostname, {})
                
                target_scrape = scaling.get("scrape", 0)
                target_details = scaling.get("details", 0)
                
                # Update environment for delay
                if "google_maps_delay_seconds" in prospecting:
                    os.environ["GOOGLE_MAPS_DELAY_SECONDS"] = str(prospecting["google_maps_delay_seconds"])

                # 2. Adjust Scrape Tasks
                while len(scrape_tasks) < target_scrape:
                    new_id = len(scrape_tasks)
                    logger.info(f"Scaling UP: Starting Scrape Task {new_id}")
                    task = asyncio.create_task(_run_scrape_task_loop(browser, scrape_queue, gm_list_item_queue, s3_client, bucket_name, debug))
                    scrape_tasks[new_id] = task
                
                while len(scrape_tasks) > target_scrape:
                    old_id = max(scrape_tasks.keys())
                    logger.info(f"Scaling DOWN: Stopping Scrape Task {old_id}")
                    scrape_tasks[old_id].cancel()
                    del scrape_tasks[old_id]

                # 3. Adjust Details Tasks
                while len(details_tasks) < target_details:
                    new_id = len(details_tasks)
                    logger.info(f"Scaling UP: Starting Details Task {new_id}")
                    # We need a tracker for details tasks if we want bandwidth logging
                    # For supervisor, we'll create a context per task loop or share one?
                    # _run_details_task_loop expects a browser or context. 
                    # If we give it a browser, it will create its own pages.
                    task = asyncio.create_task(_run_details_task_loop(browser, gm_list_item_queue, enrichment_queue, s3_client, bucket_name, debug, False, processed_by))
                    details_tasks[new_id] = task

                while len(details_tasks) > target_details:
                    old_id = max(details_tasks.keys())
                    logger.info(f"Scaling DOWN: Stopping Details Task {old_id}")
                    details_tasks[old_id].cancel()
                    del details_tasks[old_id]

                logger.info(f"Supervisor Heartbeat: {len(scrape_tasks)} Scrape, {len(details_tasks)} Details tasks active.")

            except Exception as e:
                logger.error(f"Supervisor loop error: {e}")

            await asyncio.sleep(interval)

@app.command()
def scrape(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name."),
    headed: bool = typer.Option(False, "--headed", help="Run browser in headed mode."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging."),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of concurrent workers.")
) -> None:
    """
    Starts a worker node that polls for scrape tasks and executes them.
    """
    effective_campaign = campaign
    if not effective_campaign:
        effective_campaign = os.getenv("CAMPAIGN_NAME")
    if not effective_campaign:
        effective_campaign = get_campaign()
    
    # We set up logging after we might know the campaign, but worker log files are generic
    log_level = logging.DEBUG if debug else logging.INFO
    setup_file_logging("worker_scrape", console_level=log_level)
    
    logger.info(f"Effective campaign: {effective_campaign}")
    
    if not effective_campaign:
        logger.error("No campaign specified and no active context.")
        raise typer.Exit(1)

    # Load scraper settings from campaign config if available
    config = load_campaign_config(effective_campaign)
    prospecting_config = config.get("prospecting", {})
    
    # Resolve worker count: CLI > Config > Default(1)
    final_workers = workers
    if final_workers == 1: # Default value from Typer
        final_workers = prospecting_config.get("scrape_workers", 1)

    # Optional override of global scraper settings
    if "google_maps_delay_seconds" in prospecting_config:
        os.environ["GOOGLE_MAPS_DELAY_SECONDS"] = str(prospecting_config["google_maps_delay_seconds"])

    asyncio.run(run_worker(not headed, debug, effective_campaign, workers=final_workers))

@app.command()
def details(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name."),
    headed: bool = typer.Option(False, "--headed", help="Run browser in headed mode."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging."),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of concurrent workers.")
) -> None:
    """
    Starts a worker node that polls for details tasks (Place IDs) and scrapes them.
    """
    effective_campaign = campaign
    if not effective_campaign:
        effective_campaign = os.getenv("CAMPAIGN_NAME")
    if not effective_campaign:
        effective_campaign = get_campaign()
        
    log_level = logging.DEBUG if debug else logging.INFO
    setup_file_logging("worker_details", console_level=log_level)

    logger.info(f"Effective campaign: {effective_campaign}")

    if not effective_campaign:
        logger.error("No campaign specified and no active context.")
        raise typer.Exit(1)

    # Load scraper settings from campaign config if available
    config = load_campaign_config(effective_campaign)
    prospecting_config = config.get("prospecting", {})
    
    # Resolve worker count: CLI > Config > Default(1)
    final_workers = workers
    if final_workers == 1: # Default value from Typer
        final_workers = prospecting_config.get("details_workers", 1)

    if "google_maps_delay_seconds" in prospecting_config:
        os.environ["GOOGLE_MAPS_DELAY_SECONDS"] = str(prospecting_config["google_maps_delay_seconds"])

    asyncio.run(run_details_worker(not headed, debug, effective_campaign, workers=final_workers))
