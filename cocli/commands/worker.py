import csv
import socket
import time
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Any, Dict, List
from rich.console import Console
from playwright.async_api import async_playwright

import os
import asyncio
import logging
import typer
import boto3
from cocli.core.text_utils import slugify

from cocli.core.logging_config import setup_file_logging
from cocli.core.queue.factory import get_queue_manager
from cocli.scrapers.google_maps import scrape_google_maps
from cocli.scrapers.google_maps_details import scrape_google_maps_details
from cocli.models.scrape_task import GmItemTask, ScrapeTask
from cocli.models.google_maps_prospect import GoogleMapsProspect
from cocli.models.queue import QueueMessage
from cocli.core.prospects_csv_manager import ProspectsIndexManager
from cocli.core.config import load_campaign_config, get_campaigns_dir, get_campaign
from cocli.utils.playwright_utils import setup_optimized_context


# Load Version
def get_version() -> str:
    # 1. Try file in project root (dev mode)
    try:
        root_version = Path(__file__).parent.parent.parent / "VERSION"
        if root_version.exists():
            return root_version.read_text().strip()
    except Exception:
        pass

    # 2. Try file in package dir (installed mode)
    try:
        pkg_version = Path(__file__).parent.parent / "VERSION"
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

    logger.warning(
        f"Local config for '{campaign_name}' not found at {config_path}. Attempting to fetch from S3..."
    )

    # Determine AWS profile for initial bootstrap
    profile_name = os.getenv("AWS_PROFILE")
    if profile_name and profile_name.strip():
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
                logger.warning(f"Failed to fetch s3://{b}/{key}: {e}")
                continue

    logger.error(f"Failed to fetch config for '{campaign_name}' from S3.")


async def run_worker(
    headless: bool, debug: bool, campaign_name: str, workers: int = 1
) -> None:
    try:
        ensure_campaign_config(campaign_name)

        # Determine AWS profile for S3 client
        config = load_campaign_config(campaign_name)
        aws_config = config.get("aws", {})
        bucket_name = (
            aws_config.get("cocli_data_bucket_name") or f"cocli-data-{campaign_name}"
        )

        if os.getenv("COCLI_RUNNING_IN_FARGATE"):
            profile_name = None
        else:
            profile_name = aws_config.get("profile") or aws_config.get("aws_profile")

        if profile_name:
            session = boto3.Session(profile_name=profile_name)
        else:
            session = boto3.Session()
        s3_client = session.client("s3")

        scrape_queue = get_queue_manager(
            "scrape_tasks",
            use_cloud=True,
            queue_type="scrape",
            campaign_name=campaign_name,
        )
        gm_list_item_queue = get_queue_manager(
            "gm_list_item",
            use_cloud=True,
            queue_type="gm_list_item",
            campaign_name=campaign_name,
        )
    except Exception as e:
        logger.error(f"Configuration Error: {e}")
        return

    logger.info(
        f"Worker v{VERSION} started for campaign '{campaign_name}' with {workers} worker(s). Polling for tasks..."
    )

    async with async_playwright() as p:
        while True:  # Browser Restart Loop
            logger.info("Launching browser...")
            browser = None
            try:
                browser = await p.chromium.launch(
                    headless=headless,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-accelerated-2d-canvas",
                        "--no-first-run",
                        "--no-zygote",
                        "--disable-gpu",
                        "--disable-software-rasterizer",
                    ],
                )

                # Create context and setup optimizations for bandwidth tracking
                context = await browser.new_context()
                tracker = await setup_optimized_context(context)

                tasks = [
                    _run_scrape_task_loop(
                        context,
                        scrape_queue,
                        gm_list_item_queue,
                        s3_client,
                        bucket_name,
                        debug,
                        tracker=tracker,
                    )
                    for _ in range(workers)
                ]
                await asyncio.gather(*tasks)

            except Exception as e:
                logger.error(f"Worker Error: {e}")

            finally:
                if "browser" in locals() and browser:
                    try:
                        await browser.close()
                    except Exception:
                        pass
                logger.info("Restarting browser session in 5 seconds...")
                await asyncio.sleep(5)


async def execute_cli_command(args: Optional[List[str]]) -> bool:
    """Executes a cocli command via subprocess."""
    if not args:
        logger.error("No arguments provided to execute_cli_command")
        return False
    try:
        # Avoid double 'cocli' prefix
        cmd = list(args)
        if cmd[0] != "cocli":
            cmd = ["cocli"] + cmd
        
        logger.info(f"Executing remote command: {' '.join(cmd)}")
        
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            logger.info(f"Command succeeded: {result.stdout.strip()}")
            return True
        else:
            logger.error(f"Command failed (exit {result.returncode}): {result.stderr.strip()}")
            return False
    except Exception as e:
        logger.error(f"Error executing remote command: {e}")
        return False

async def _run_command_poller_loop(command_queue: Any, s3_client: Any, bucket_name: str, campaign_name: str, aws_config: Dict[str, Any]) -> None:
    """Polls SQS for campaign update commands and executes them."""
    print(f"!!! COMMAND POLLER INIT START for {campaign_name} !!!", flush=True)
    from ..core.reporting import get_exclusions_data, get_queries_data, get_locations_data
    from ..application.campaign_service import CampaignService
    import json
    import shlex

    while True:
        try:
            # Re-init service in case of config changes
            try:
                campaign_service = CampaignService(campaign_name)
            except Exception as init_err:
                logger.error(f"Failed to init CampaignService: {init_err}")
                await asyncio.sleep(10)
                continue

            commands = await asyncio.to_thread(command_queue.poll, batch_size=1)
            for cmd in commands:
                logger.info(f"Executing remote command: {cmd.command}")
                
                # We now parse the command string or use args if they look like a service call
                # Format from JS: "add-exclude <id>", "remove-exclude <id>", etc.
                success = False
                parts = shlex.split(cmd.command)
                
                # Check for direct service commands
                if "add-exclude" in cmd.command:
                    # identifier is usually the next part
                    idx = parts.index("add-exclude")
                    if idx + 1 < len(parts):
                        success = await asyncio.to_thread(campaign_service.add_exclude, parts[idx+1])
                elif "remove-exclude" in cmd.command:
                    idx = parts.index("remove-exclude")
                    if idx + 1 < len(parts):
                        success = await asyncio.to_thread(campaign_service.remove_exclude, parts[idx+1])
                elif "add-query" in cmd.command:
                    idx = parts.index("add-query")
                    if idx + 1 < len(parts):
                        success = await asyncio.to_thread(campaign_service.add_query, parts[idx+1])
                elif "remove-query" in cmd.command:
                    idx = parts.index("remove-query")
                    if idx + 1 < len(parts):
                        success = await asyncio.to_thread(campaign_service.remove_query, parts[idx+1])
                elif "add-location" in cmd.command:
                    idx = parts.index("add-location")
                    if idx + 1 < len(parts):
                        success = await asyncio.to_thread(campaign_service.add_location, parts[idx+1])
                elif "remove-location" in cmd.command:
                    idx = parts.index("remove-location")
                    if idx + 1 < len(parts):
                        success = await asyncio.to_thread(campaign_service.remove_location, parts[idx+1])
                else:
                    # Fallback to CLI for anything else
                    success = await execute_cli_command(cmd.args or parts)
                
                if success:
                    # Identify which granular report to update
                    report_type = None
                    data = {}
                    
                    if "exclude" in cmd.command:
                        report_type = "exclusions"
                        data = get_exclusions_data(campaign_name)
                    elif "query" in cmd.command:
                        report_type = "queries"
                        data = get_queries_data(campaign_name)
                    elif "location" in cmd.command:
                        report_type = "locations"
                        data = get_locations_data(campaign_name)
                    
                    if report_type:
                        # 1. Immediate Sync-UP of indexes to S3 (so other workers see it)
                        from ..utils.smart_sync_up import run_smart_sync_up
                        from ..core.config import get_cocli_base_dir
                        
                        logger.info(f"Performing immediate sync-up of indexes for {campaign_name}")
                        local_base = get_cocli_base_dir()
                        await asyncio.to_thread(
                            run_smart_sync_up, 
                            "indexes", 
                            bucket_name, 
                            "indexes/", 
                            local_base / "indexes", 
                            campaign_name, 
                            aws_config, 
                            delete_remote=False
                        )

                        web_bucket = aws_config.get("cocli_web_bucket_name")
                        if web_bucket:
                            # 1. Upload targeted JSON
                            report_key = f"reports/{report_type}.json"
                            logger.info(f"Uploading targeted report: {report_key}")
                            s3_client.put_object(
                                Bucket=web_bucket,
                                Key=report_key,
                                Body=json.dumps(data, indent=2),
                                ContentType="application/json"
                            )
                            
                            # 2. Trigger CloudFront Invalidation for this specific file
                            try:
                                cf = boto3.client("cloudfront")
                                domain = aws_config.get("hosted-zone-domain")
                                subdomain = f"cocli.{domain}"
                                
                                # Find distribution ID
                                dists = cf.list_distributions().get("DistributionList", {}).get("Items", [])
                                dist_id = next((d["Id"] for d in dists if subdomain in d.get("Aliases", {}).get("Items", [])), None)
                                
                                if dist_id:
                                    logger.info(f"Invalidating CloudFront cache for /{report_key}")
                                    cf.create_invalidation(
                                        DistributionId=dist_id,
                                        InvalidationBatch={
                                            'Paths': {
                                                'Quantity': 1,
                                                'Items': [f"/{report_key}"]
                                            },
                                            'CallerReference': str(time.time())
                                        }
                                    )
                            except Exception as cf_err:
                                logger.warning(f"Could not invalidate CloudFront: {cf_err}")

                    await asyncio.to_thread(command_queue.ack, cmd)
                else:
                    await asyncio.to_thread(command_queue.ack, cmd)
                    
        except asyncio.CancelledError:
            logger.info("Command Poller stopping...")
            break
        except Exception as e:
            logger.error(f"Command Poller error: {e}")
            await asyncio.sleep(10)
        
        await asyncio.sleep(5)

async def _run_scrape_task_loop(
    browser_or_context: Any,
    scrape_queue: Any,
    gm_list_item_queue: Any,
    s3_client: Any,
    bucket_name: str,
    debug: bool,
    tracker: Optional[Any] = None,
) -> None:
    while True:  # Task Processing Loop
        # BrowserContext doesn't have is_connected, check the browser if possible
        connected = True
        if hasattr(browser_or_context, "is_connected"):
            connected = browser_or_context.is_connected()
        elif hasattr(browser_or_context, "browser") and browser_or_context.browser:
            connected = browser_or_context.browser.is_connected()

        if not connected:
            logger.error("Browser is disconnected. Breaking task loop to restart.")
            break

        tasks: List[ScrapeTask] = scrape_queue.poll(batch_size=1)

        if not tasks:
            await asyncio.sleep(5)
            continue

        task = tasks[0]  # batch_size=1

        # Identify Mode
        grid_tiles = None
        if task.tile_id:
            logger.info(f"Grid Task ({task.tile_id}): {task.search_phrase}")
            grid_tiles = [
                {
                    "id": task.tile_id,
                    "center_lat": task.latitude,
                    "center_lon": task.longitude,
                    "center": {"lat": task.latitude, "lon": task.longitude},
                }
            ]
        else:
            logger.info(
                f"Point Task: {task.search_phrase} @ {task.latitude}, {task.longitude}"
            )

        start_mb = tracker.get_mb() if tracker else 0.0

        try:
            location_param = {
                "latitude": str(task.latitude),
                "longitude": str(task.longitude),
            }
            csv_manager = ProspectsIndexManager(task.campaign_name)
            prospect_count = 0

            # Heartbeat task for FilesystemQueue
            heartbeat_task = None
            if hasattr(scrape_queue, "heartbeat") and task.ack_token:

                async def _heartbeat_loop() -> None:
                    try:
                        while True:
                            await asyncio.sleep(60)
                            scrape_queue.heartbeat(task.ack_token)
                    except asyncio.CancelledError:
                        pass

                heartbeat_task = asyncio.create_task(_heartbeat_loop())

            try:
                async with asyncio.timeout(900):
                    # For point-based or tile-based scrapes, we can pass context here if needed,
                    # but scrape_google_maps currently takes page/browser? No, it takes context/browser.
                    # Note: scrape_google_maps creates its own pages from the browser instance.
                    async for prospect in scrape_google_maps(
                        browser=browser_or_context,
                        location_param=location_param,
                        search_strings=[task.search_phrase],
                        campaign_name=task.campaign_name,
                        grid_tiles=grid_tiles,
                        debug=debug,
                        s3_client=s3_client,
                        s3_bucket=bucket_name,
                    ):
                        if not prospect.Place_ID:
                            continue

                        prospect_count += 1
                        if csv_manager.append_prospect(prospect):
                            if s3_client:
                                file_path = csv_manager.get_file_path(prospect.Place_ID)
                                s3_key = f"campaigns/{task.campaign_name}/indexes/google_maps_prospects/{file_path.name}"
                                try:
                                    s3_client.upload_file(
                                        str(file_path), bucket_name, s3_key
                                    )
                                except Exception:
                                    pass

                            details_task = GmItemTask(
                                place_id=prospect.Place_ID,
                                campaign_name=task.campaign_name,
                                force_refresh=False,
                                ack_token=None,
                            )
                            gm_list_item_queue.push(details_task)
            finally:
                if heartbeat_task:
                    heartbeat_task.cancel()
                    try:
                        await asyncio.wait_for(heartbeat_task, timeout=2)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass

            if tracker:
                logger.info(
                    f"Task Complete. Found {prospect_count} prospects. Bandwidth: {tracker.get_mb() - start_mb:.2f} MB"
                )
            else:
                logger.info(f"Task Complete. Found {prospect_count} prospects.")

            scrape_queue.ack(task)

        except Exception as e:
            logger.error(f"Task Failed: {e}")
            scrape_queue.nack(task)
            if (
                "Target page, context or browser has been closed" in str(e)
                or not connected
            ):
                logger.critical("Browser fatal error detected.")
                break


async def run_details_worker(
    headless: bool,
    debug: bool,
    campaign_name: str,
    once: bool = False,
    processed_by: Optional[str] = None,
    browser: Optional[Any] = None,
    workers: int = 1,
) -> None:
    if not processed_by:
        processed_by = f"local-worker-{socket.gethostname()}"
    try:
        ensure_campaign_config(campaign_name)

        # Determine AWS profile for S3 client
        config = load_campaign_config(campaign_name)
        aws_config = config.get("aws", {})
        bucket_name = (
            aws_config.get("cocli_data_bucket_name") or f"cocli-data-{campaign_name}"
        )

        if os.getenv("COCLI_RUNNING_IN_FARGATE"):
            profile_name = None
        else:
            profile_name = aws_config.get("profile") or aws_config.get("aws_profile")

        if profile_name:
            session = boto3.Session(profile_name=profile_name)
        else:
            session = boto3.Session()
        s3_client = session.client("s3")

        gm_list_item_queue = get_queue_manager(
            "gm_list_item",
            use_cloud=True,
            queue_type="gm_list_item",
            campaign_name=campaign_name,
        )
        enrichment_queue = get_queue_manager(
            "enrichment",
            use_cloud=True,
            queue_type="enrichment",
            campaign_name=campaign_name,
        )

        if hasattr(gm_list_item_queue, "queue_url"):
            logger.info(
                f"run_details_worker: Using GM List Item Queue URL: {gm_list_item_queue.queue_url}"
            )

    except Exception as e:
        logger.error(f"Configuration Error: {e}")
        return

    logger.info(
        f"Details Worker v{VERSION} started for campaign '{campaign_name}' with {workers} worker(s). Polling for tasks..."
    )

    if browser:
        # We need a context to setup the tracker
        # For simplicity in the provided browser case, we'll skip optimization
        # unless we want to refactor the caller to provide a context.
        tasks = [
            _run_details_task_loop(
                browser,
                gm_list_item_queue,
                enrichment_queue,
                s3_client,
                bucket_name,
                debug,
                once,
                processed_by,
            )
            for _ in range(workers)
        ]
        await asyncio.gather(*tasks)
    else:
        async with async_playwright() as p:
            while True:  # Browser Restart Loop
                logger.info("Launching browser...")
                browser_instance = None
                try:
                    browser_instance = await p.chromium.launch(
                        headless=headless,
                        args=[
                            "--no-sandbox",
                            "--disable-setuid-sandbox",
                            "--disable-dev-shm-usage",
                            "--disable-accelerated-2d-canvas",
                            "--no-first-run",
                            "--no-zygote",
                            "--disable-gpu",
                            "--disable-software-rasterizer",
                        ],
                    )

                    # Create context and setup optimizations
                    context = await browser_instance.new_context(ignore_https_errors=True)
                    tracker = await setup_optimized_context(context)

                    tasks = [
                        _run_details_task_loop(
                            context,
                            gm_list_item_queue,
                            enrichment_queue,
                            s3_client,
                            bucket_name,
                            debug,
                            once,
                            processed_by,
                            tracker=tracker,
                        )
                        for _ in range(workers)
                    ]
                    await asyncio.gather(*tasks)
                    await browser_instance.close()
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


async def _run_details_task_loop(
    browser_or_context: Any,
    gm_list_item_queue: Any,
    enrichment_queue: Any,
    s3_client: Any,
    bucket_name: str,
    debug: bool,
    once: bool,
    processed_by: str,
    tracker: Optional[Any] = None,
) -> None:
    while True:  # Task Loop
        # BrowserContext doesn't have is_connected, check the browser if possible
        connected = True
        if hasattr(browser_or_context, "is_connected"):
            connected = browser_or_context.is_connected()
        elif hasattr(browser_or_context, "browser") and browser_or_context.browser:
            connected = browser_or_context.browser.is_connected()

        if not connected:
            logger.error("Browser is disconnected. Restarting.")
            break

        tasks: List[GmItemTask] = gm_list_item_queue.poll(batch_size=1)
        if not tasks:
            if once:
                logger.info(
                    "run_details_worker(once=True): No tasks found in GM List Item queue."
                )
                return  # Exit if in single-run mode and queue empty
            await asyncio.sleep(5)
            continue

        task = tasks[0]  # batch_size=1
        logger.info(f"Detail Task found: {task.place_id}")

        start_mb = tracker.get_mb() if tracker else 0.0

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
                    with open(file_path, "r", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        existing_data = next(reader, None)
                        if existing_data:
                            existing_prospect = GoogleMapsProspect.model_validate(
                                existing_data
                            )
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
                            logger.info(
                                f"Skipping scrape for {task.place_id}. Data is fresh ({max(0, int(age_days))} days old)."
                            )

                            # Ensure it's in the enrichment queue if it has a domain
                            if existing_prospect.Domain and existing_prospect.Name:
                                msg = QueueMessage(
                                    domain=existing_prospect.Domain,
                                    company_slug=slugify(existing_prospect.Name),
                                    campaign_name=task.campaign_name,
                                    force_refresh=task.force_refresh,
                                    ack_token=None,
                                )
                                enrichment_queue.push(msg)

                            gm_list_item_queue.ack(task)
                            if once:
                                return
                            continue

            # 3. Proceed with Scrape
            # Heartbeat task for FilesystemQueue
            heartbeat_task = None
            if hasattr(gm_list_item_queue, "heartbeat") and task.ack_token:

                async def _heartbeat_loop() -> None:
                    try:
                        while True:
                            await asyncio.sleep(60)
                            gm_list_item_queue.heartbeat(task.ack_token)
                    except asyncio.CancelledError:
                        pass

                heartbeat_task = asyncio.create_task(_heartbeat_loop())

            try:
                page = await browser_or_context.new_page()
                try:
                    detailed_prospect_data = await scrape_google_maps_details(
                        page=page,
                        place_id=task.place_id,
                        campaign_name=task.campaign_name,
                        debug=debug,
                    )
                finally:
                    await page.close()
            finally:
                if heartbeat_task:
                    heartbeat_task.cancel()
                    try:
                        await asyncio.wait_for(heartbeat_task, timeout=2)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass

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
                    ack_token=None,
                )
                enrichment_queue.push(msg)
                logger.info(f"Pushed {final_prospect_data.Domain} to Enrichment Queue")

            # --- Email Indexing ---
            # If the GMB details scrape found an email, index it immediately
            # Note: GMB Parser doesn't always find emails, but if it does, we want it.
            if hasattr(final_prospect_data, "Email") and final_prospect_data.Email:
                try:
                    from cocli.core.email_index_manager import EmailIndexManager
                    from cocli.models.email import EmailEntry

                    email_manager = EmailIndexManager(task.campaign_name)
                    entry = EmailEntry(
                        email=final_prospect_data.Email,
                        domain=final_prospect_data.Domain
                        or final_prospect_data.Email.split("@")[-1],
                        company_slug=final_prospect_data.company_slug,
                        source="gmb_details_worker",
                        tags=[task.campaign_name],
                    )
                    email_manager.add_email(entry)
                    logger.info(
                        f"Indexed email from GMB details: {final_prospect_data.Email}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to index email from GMB details: {e}")
            # ----------------------

            if tracker:
                logger.info(
                    f"Detailing Complete for {task.place_id}. Bandwidth: {tracker.get_mb() - start_mb:.2f} MB"
                )
            else:
                logger.info(f"Detailing Complete for {task.place_id}.")

            gm_list_item_queue.ack(task)

            if once:
                return  # Success - return to main loop

        except Exception as e:
            logger.error(f"Detail Task Failed for {task.place_id}: {e}")
            gm_list_item_queue.nack(task)
            if once:
                return

            connected = True
            if hasattr(browser_or_context, "is_connected"):
                connected = browser_or_context.is_connected()
            elif hasattr(browser_or_context, "browser") and browser_or_context.browser:
                connected = browser_or_context.browser.is_connected()

            if (
                "Target page, context or browser has been closed" in str(e)
                or not connected
            ):
                logger.critical("Browser fatal error detected.")
                break


async def run_enrichment_worker(
    headless: bool,
    debug: bool,
    campaign_name: str,
    once: bool = False,
    processed_by: Optional[str] = None,
    browser: Optional[Any] = None,
    workers: int = 1,
    use_cloud: bool = True,
) -> None:
    if not processed_by:
        processed_by = f"enrichment-worker-{socket.gethostname()}"
    try:
        ensure_campaign_config(campaign_name)
        # Check if we should override cloud queue based on environment
        effective_use_cloud = use_cloud
        if os.getenv("COCLI_QUEUE_TYPE") == "filesystem":
            effective_use_cloud = False

        enrichment_queue = get_queue_manager(
            "enrichment",
            use_cloud=effective_use_cloud,
            queue_type="enrichment",
            campaign_name=campaign_name,
        )
    except Exception as e:
        logger.error(f"Configuration Error: {e}")
        return

    logger.info(
        f"Enrichment Worker v{VERSION} started for campaign '{campaign_name}' with {workers} worker(s). Polling for tasks..."
    )

    if browser:
        tasks = [
            _run_enrichment_task_loop(
                browser, enrichment_queue, debug, once, processed_by, campaign_name
            )
            for _ in range(workers)
        ]
        await asyncio.gather(*tasks)
    else:
        async with async_playwright() as p:
            while True:
                logger.info("Launching browser...")
                browser_instance = None
                try:
                    logger.info(f"Attempting chromium.launch (headless={headless})...")
                    browser_instance = await p.chromium.launch(
                        headless=headless,
                        args=["--no-sandbox"]
                    )
                    logger.info("Browser launched. Creating context...")

                    # Create context and setup optimizations
                    context = await browser_instance.new_context(ignore_https_errors=True)
                    logger.info("Context created. Setting up optimizations...")
                    tracker = await setup_optimized_context(context)
                    logger.info("Optimizations set up. Starting task loops...")

                    tasks = [
                        _run_enrichment_task_loop(
                            context,
                            enrichment_queue,
                            debug,
                            once,
                            processed_by,
                            campaign_name,
                            tracker=tracker,
                        )
                        for _ in range(workers)
                    ]
                    await asyncio.gather(*tasks)
                    await browser_instance.close()
                    if once:
                        break
                except Exception as e:
                    logger.error(f"Enrichment Worker Error: {e}")
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


async def _run_enrichment_task_loop(
    browser_or_context: Any,
    enrichment_queue: Any,
    debug: bool,
    once: bool,
    processed_by: str,
    campaign_name: str,
    s3_client: Optional[Any] = None,
    bucket_name: Optional[str] = None,
    tracker: Optional[Any] = None,
) -> None:
    from cocli.core.enrichment import enrich_company_website
    from cocli.models.company import Company
    from cocli.models.campaign import Campaign
    from cocli.core.s3_company_manager import S3CompanyManager

    try:
        campaign_obj = Campaign.load(campaign_name)
    except Exception as e:
        logger.error(f"Could not load Campaign '{campaign_name}': {e}")
        if once:
            return
        await asyncio.sleep(10)
        return

    # Initialize S3 manager for immediate pushes
    s3_company_manager = None
    if s3_client and bucket_name:
        try:
            s3_company_manager = S3CompanyManager(campaign=campaign_obj)
            # Ensure it uses the shared client
            s3_company_manager.s3_client = s3_client
            s3_company_manager.s3_bucket_name = bucket_name
        except Exception as e:
            logger.warning(f"Could not initialize S3CompanyManager for immediate push: {e}")

    while True:
        connected = True
        if hasattr(browser_or_context, "is_connected"):
            connected = browser_or_context.is_connected()
        elif hasattr(browser_or_context, "browser") and browser_or_context.browser:
            connected = browser_or_context.browser.is_connected()

        if not connected:
            logger.error("Browser is disconnected. Breaking task loop to restart.")
            break

        tasks: List[QueueMessage] = enrichment_queue.poll(batch_size=1)
        if not tasks:
            if once:
                logger.info(
                    "run_enrichment_worker(once=True): No tasks found in Enrichment queue."
                )
                return
            await asyncio.sleep(5)
            continue

        task = tasks[0]
        logger.info(f"Enrichment Task found: {task.domain}")
        start_mb = tracker.get_mb() if tracker else 0.0

        try:
            company = Company.get(task.company_slug) or Company(
                name=task.company_slug, domain=task.domain, slug=task.company_slug
            )

            # Heartbeat task for FilesystemQueue
            heartbeat_task = None
            if hasattr(enrichment_queue, "heartbeat") and task.ack_token:

                async def _heartbeat_loop() -> None:
                    try:
                        while True:
                            await asyncio.sleep(60)
                            enrichment_queue.heartbeat(task.ack_token)
                    except asyncio.CancelledError:
                        pass

                heartbeat_task = asyncio.create_task(_heartbeat_loop())

            try:
                website_data = await enrich_company_website(
                    browser=browser_or_context,
                    company=company,
                    campaign=campaign_obj,
                    force=task.force_refresh,
                    debug=debug,
                )
            finally:
                if heartbeat_task:
                    heartbeat_task.cancel()
                    try:
                        await asyncio.wait_for(heartbeat_task, timeout=2)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass

            if website_data:
                # 1. Save enrichment data locally (website.md)
                website_data.save(task.company_slug)
                
                # 2. Update Company object with newly discovered data
                if website_data.email and not company.email:
                    company.email = website_data.email
                
                if website_data.phone and not company.phone_number:
                    company.phone_number = website_data.phone
                
                for kw in website_data.found_keywords:
                    if kw not in company.keywords:
                        company.keywords.append(kw)
                
                for tech in website_data.found_keywords:
                    if tech not in company.tech_stack:
                        company.tech_stack.append(tech)
                
                # Merge social links
                for platform in ["facebook", "linkedin", "instagram", "twitter", "youtube"]:
                    attr = f"{platform}_url"
                    new_val = getattr(website_data, attr)
                    if new_val and not getattr(company, attr):
                        setattr(company, attr, new_val)

                # 3. Save company locally and push to S3 immediately
                company.save()
                if s3_company_manager:
                    logger.info(f"Pusing updated company index and website enrichment to S3 for {task.company_slug}")
                    await s3_company_manager.save_company_index(company)
                    await s3_company_manager.save_website_enrichment(task.company_slug, website_data)

                if tracker:
                    logger.info(
                        f"Enrichment Complete for {task.domain}. Bandwidth: {tracker.get_mb() - start_mb:.2f} MB"
                    )
                else:
                    logger.info(f"Enrichment Complete for {task.domain}.")
                enrichment_queue.ack(task)
            else:
                logger.warning(f"Enrichment failed for {task.domain}.")
                enrichment_queue.ack(task)

            if once:
                return
        except Exception as e:
            logger.error(f"Enrichment Task Failed for {task.domain}: {e}")
            enrichment_queue.nack(task)
            await asyncio.sleep(5)  # Avoid immediate tight loop on failure
            if once:
                return

            if (
                "Target page, context or browser has been closed" in str(e)
                or not connected
            ):
                logger.critical("Browser fatal error detected.")
                break


@app.command()
def supervisor(
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name."
    ),
    headed: bool = typer.Option(False, "--headed", help="Run browser in headed mode."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging."),
    interval: int = typer.Option(
        60, "--interval", help="Seconds between config checks."
    ),
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


def sync_active_leases_to_s3(
    campaign_name: str, s3_client: Any, bucket_name: str
) -> None:
    """
    Pushes local lease files to S3 so they are visible in global reports. (V2 structure)
    """
    from ..core.config import get_cocli_base_dir
    
    queue_base = get_cocli_base_dir() / "data" / "queues" / campaign_name / "enrichment"
    pending_dir = queue_base / "pending"

    if not pending_dir.exists():
        return

    try:
        # Scan for lease.json in all task directories
        for task_dir in pending_dir.iterdir():
            if not task_dir.is_dir():
                continue
            
            lease_file = task_dir / "lease.json"
            if lease_file.exists():
                # S3 Key: campaigns/<campaign>/queues/enrichment/pending/<hash>/lease.json
                task_id = task_dir.name
                s3_key = f"campaigns/{campaign_name}/queues/enrichment/pending/{task_id}/lease.json"
                s3_client.upload_file(str(lease_file), bucket_name, s3_key)

    except Exception as e:
        logger.warning(f"Failed to sync V2 leases to S3: {e}")


async def run_supervisor(
    headless: bool, debug: bool, campaign_name: str, interval: int
) -> None:
    from ..core.config import load_campaign_config
    import socket
    import asyncio

    hostname = os.getenv("COCLI_HOSTNAME") or socket.gethostname().split(".")[0]
    once = False  # Supervisor always runs in a loop

    logger.info(
        f"Supervisor started on host '{hostname}' for campaign '{campaign_name}'."
    )

    # Suppress verbose logs from boto3 and urllib3
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("s3transfer").setLevel(logging.WARNING)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--no-first-run",
                "--no-zygote",
                "--disable-gpu",
                "--disable-software-rasterizer",
            ],
        )

        scrape_tasks: Dict[int, asyncio.Task[Any]] = {}

        details_tasks: Dict[int, asyncio.Task[Any]] = {}

        enrichment_tasks: Dict[int, asyncio.Task[Any]] = {}

        command_task: Optional[asyncio.Task[Any]] = None

        # Shared context and tracker for all workers on this host
        context = await browser.new_context(ignore_https_errors=True)
        tracker = await setup_optimized_context(context)

        # Setup queues and clients once
        ensure_campaign_config(campaign_name)
        config = load_campaign_config(campaign_name)
        aws_config = config.get("aws", {})
        bucket_name = aws_config.get("cocli_data_bucket_name")
        
        # Resolve AWS session/client
        aws_profile = os.getenv("AWS_PROFILE") or aws_config.get("profile")
        session = boto3.Session(profile_name=aws_profile)
        s3_client = session.client("s3")

        # Initialize Queues
        scrape_queue = get_queue_manager("scrape", use_cloud=True, queue_type="scrape", campaign_name=campaign_name)
        gm_list_item_queue = get_queue_manager("details", use_cloud=True, queue_type="gm_list_item", campaign_name=campaign_name)
        enrichment_queue = get_queue_manager("enrichment", use_cloud=True, queue_type="enrichment", campaign_name=campaign_name)
        command_queue = get_queue_manager("command", use_cloud=True, queue_type="command", campaign_name=campaign_name)

        # Sync Throttling
        from ..core.config import get_cocli_base_dir
        from .smart_sync import run_smart_sync
        from ..utils.smart_sync_up import run_smart_sync_up
        local_base = get_cocli_base_dir()
        last_sync_time: float = 0.0
        sync_interval_seconds = 3600 # 60 minutes (Real-time push handles most data)
        processed_by = f"{hostname}-supervisor"

        while True:
            try:
                # Start/Restart command poller if it dies
                if command_task is None or command_task.done():
                    if command_task and command_task.done() and command_task.exception():
                        logger.error(f"Command poller died with exception: {command_task.exception()}")
                    logger.info("Starting (or restarting) command poller...")
                    command_task = asyncio.create_task(_run_command_poller_loop(command_queue, s3_client, bucket_name, campaign_name, aws_config))
                
                # 0. Sync config from S3 (Throttled or in thread)
                await asyncio.to_thread(sync_campaign_config, campaign_name)

                # 1. Reload Config (from local file, which should be synced from S3)
                config = load_campaign_config(campaign_name)
                prospecting = config.get("prospecting", {})
                scaling = prospecting.get("scaling", {}).get(hostname, {})

                target_scrape = scaling.get("gm-list", scaling.get("scrape", 0))
                target_details = scaling.get("gm-details", scaling.get("details", 0))
                target_enrich = scaling.get("enrichment", 0)

                # Update environment for delay
                if "google_maps_delay_seconds" in prospecting:
                    os.environ["GOOGLE_MAPS_DELAY_SECONDS"] = str(
                        prospecting["google_maps_delay_seconds"]
                    )

                # 2. Adjust Scrape Tasks
                while len(scrape_tasks) < target_scrape:
                    new_id = len(scrape_tasks)
                    logger.info(f"Scaling UP: Starting Scrape Task {new_id}")
                    task = asyncio.create_task(
                        _run_scrape_task_loop(
                            browser,
                            scrape_queue,
                            gm_list_item_queue,
                            s3_client,
                            bucket_name,
                            debug,
                        )
                    )
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
                    task = asyncio.create_task(
                        _run_details_task_loop(
                            browser,
                            gm_list_item_queue,
                            enrichment_queue,
                            s3_client,
                            bucket_name,
                            debug,
                            False,
                            processed_by,
                        )
                    )
                    details_tasks[new_id] = task

                while len(details_tasks) > target_details:
                    old_id = max(details_tasks.keys())
                    logger.info(f"Scaling DOWN: Stopping Details Task {old_id}")
                    details_tasks[old_id].cancel()
                    del details_tasks[old_id]

                # 4. Adjust Enrichment Tasks
                while len(enrichment_tasks) < target_enrich:
                    new_id = len(enrichment_tasks)
                    logger.info(f"Scaling UP: Starting Enrichment Task {new_id}")
                    # Use the shared context for all workers on this host
                    task = asyncio.create_task(
                        _run_enrichment_task_loop(
                            context,
                            enrichment_queue,
                            debug,
                            once,
                            processed_by,
                            campaign_name,
                            s3_client=s3_client,
                            bucket_name=bucket_name,
                            tracker=tracker,
                        )
                    )
                    enrichment_tasks[new_id] = task

                while len(enrichment_tasks) > target_enrich:
                    old_id = max(enrichment_tasks.keys())
                    logger.info(f"Scaling DOWN: Stopping Enrichment Task {old_id}")
                    enrichment_tasks[old_id].cancel()
                    del enrichment_tasks[old_id]

                # 0.2 Sync campaign data (V2 Queues) - throttled (AFTER starting workers)
                now = time.time()
                if now - last_sync_time > sync_interval_seconds:
                    try:
                        # 0.1 Sync leases TO S3 (Frequent is fine, but run in thread to avoid blocking)
                        await asyncio.to_thread(sync_active_leases_to_s3, campaign_name, s3_client, bucket_name)

                        companies_prefix = "companies/"
                        companies_local = local_base / "companies"
                        
                        queue_prefix = f"campaigns/{campaign_name}/queues/enrichment/pending/"
                        queue_local = local_base / "data" / "queues" / campaign_name / "enrichment" / "pending"
                        
                        logger.info("Starting throttled background sync operations (V2)")
                        # 1. Sync down new tasks
                        await asyncio.to_thread(run_smart_sync, "enrichment-queue", bucket_name, queue_prefix, queue_local, campaign_name, aws_config)
                        
                        # 2. Sync up results and leases
                        await asyncio.to_thread(run_smart_sync_up, "enrichment-queue", bucket_name, queue_prefix, queue_local, campaign_name, aws_config, delete_remote=True)
                        
                        # 3. Sync up company data
                        await asyncio.to_thread(run_smart_sync_up, "companies", bucket_name, companies_prefix, companies_local, campaign_name, aws_config, delete_remote=False, only_modified_since_minutes=60)
                        
                        # 4. Sync up index data (Exclusions, Email Index)
                        indexes_prefix = "indexes/"
                        indexes_local = local_base / "indexes"
                        await asyncio.to_thread(run_smart_sync_up, "indexes", bucket_name, indexes_prefix, indexes_local, campaign_name, aws_config, delete_remote=False)

                        # 5. Sync up completed tasks for tracking
                        completed_prefix = f"campaigns/{campaign_name}/queues/enrichment/completed/"
                        completed_local = local_base / "data" / "queues" / campaign_name / "enrichment" / "completed"
                        await asyncio.to_thread(run_smart_sync_up, "enrichment-completed", bucket_name, completed_prefix, completed_local, campaign_name, aws_config, delete_remote=False)
                        
                        # 6. Regenerate and Upload Campaign Report to Web Bucket
                        from ..core.reporting import get_campaign_stats
                        import json
                        
                        logger.info(f"Regenerating campaign report for {campaign_name}")
                        stats = get_campaign_stats(campaign_name)
                        report_json = json.dumps(stats, indent=2)
                        
                        web_bucket = aws_config.get("cocli_web_bucket_name")
                        if web_bucket:
                            report_key = f"reports/{campaign_name}.json"
                            s3_client.put_object(
                                Bucket=web_bucket,
                                Key=report_key,
                                Body=report_json,
                                ContentType="application/json"
                            )
                            logger.info(f"Uploaded updated report to s3://{web_bucket}/{report_key}")

                        last_sync_time = now
                        logger.info("Throttled background sync operations completed")
                    except Exception as e:
                        logger.warning(f"Supervisor failed to smart-sync data: {e}")

                while len(enrichment_tasks) > target_enrich:
                    old_id = max(enrichment_tasks.keys())

                    logger.info(f"Scaling DOWN: Stopping Enrichment Task {old_id}")

                    enrichment_tasks[old_id].cancel()

                    del enrichment_tasks[old_id]

                logger.info(
                    f"Supervisor Heartbeat: {len(scrape_tasks)} Scrape, {len(details_tasks)} Details, {len(enrichment_tasks)} Enrichment tasks active."
                )

            except Exception as e:
                logger.error(f"Supervisor loop error: {e}")

            await asyncio.sleep(interval)


@app.command(name="gm-list")
def gm_list(
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name."
    ),
    headed: bool = typer.Option(False, "--headed", help="Run browser in headed mode."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging."),
    workers: int = typer.Option(
        1, "--workers", "-w", help="Number of concurrent workers."
    ),
) -> None:
    """
    Starts a worker node that polls for Google Maps List tasks and executes them.
    """
    effective_campaign = campaign
    if not effective_campaign:
        effective_campaign = os.getenv("CAMPAIGN_NAME")
    if not effective_campaign:
        effective_campaign = get_campaign()

    log_level = logging.DEBUG if debug else logging.INFO
    setup_file_logging("worker_gm_list", console_level=log_level)
    logger.info(f"Effective campaign: {effective_campaign}")

    if not effective_campaign:
        logger.error("No campaign specified and no active context.")
        raise typer.Exit(1)

    config = load_campaign_config(effective_campaign)
    prospecting_config = config.get("prospecting", {})
    final_workers = workers
    if final_workers == 1:
        final_workers = prospecting_config.get("scrape_workers", 1)

    if "google_maps_delay_seconds" in prospecting_config:
        os.environ["GOOGLE_MAPS_DELAY_SECONDS"] = str(
            prospecting_config["google_maps_delay_seconds"]
        )

    asyncio.run(
        run_worker(not headed, debug, effective_campaign, workers=final_workers)
    )


@app.command(name="gm-details")
def gm_details(
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name."
    ),
    headed: bool = typer.Option(False, "--headed", help="Run browser in headed mode."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging."),
    workers: int = typer.Option(
        1, "--workers", "-w", help="Number of concurrent workers."
    ),
) -> None:
    """
    Starts a worker node that polls for Google Maps Details tasks (Place IDs) and scrapes them.
    """
    effective_campaign = campaign
    if not effective_campaign:
        effective_campaign = os.getenv("CAMPAIGN_NAME")
    if not effective_campaign:
        effective_campaign = get_campaign()

    log_level = logging.DEBUG if debug else logging.INFO
    setup_file_logging("worker_gm_details", console_level=log_level)
    logger.info(f"Effective campaign: {effective_campaign}")

    if not effective_campaign:
        logger.error("No campaign specified and no active context.")
        raise typer.Exit(1)

    config = load_campaign_config(effective_campaign)
    prospecting_config = config.get("prospecting", {})
    final_workers = workers
    if final_workers == 1:
        final_workers = prospecting_config.get("details_workers", 1)

    if "google_maps_delay_seconds" in prospecting_config:
        os.environ["GOOGLE_MAPS_DELAY_SECONDS"] = str(
            prospecting_config["google_maps_delay_seconds"]
        )

    asyncio.run(
        run_details_worker(not headed, debug, effective_campaign, workers=final_workers)
    )


@app.command()
def enrichment(
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name."
    ),
    headed: bool = typer.Option(False, "--headed", help="Run browser in headed mode."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging."),
    workers: int = typer.Option(
        1, "--workers", "-w", help="Number of concurrent workers."
    ),
) -> None:
    """

    Starts a worker node that polls for enrichment tasks (Domains) and scrapes them.

    """

    effective_campaign = campaign

    if not effective_campaign:
        effective_campaign = os.getenv("CAMPAIGN_NAME")

    if not effective_campaign:
        effective_campaign = get_campaign()

    log_level = logging.DEBUG if debug else logging.INFO

    setup_file_logging("worker_enrichment", console_level=log_level)

    logger.info(f"Effective campaign: {effective_campaign}")

    if not effective_campaign:
        logger.error("No campaign specified and no active context.")

        raise typer.Exit(1)

    # Load scraper settings from campaign config if available

    config = load_campaign_config(effective_campaign)

    prospecting_config = config.get("prospecting", {})

    # Resolve worker count: CLI > Config > Default(1)

    final_workers = workers

    if final_workers == 1:  # Default value from Typer
        final_workers = prospecting_config.get("enrichment_workers", 1)

    asyncio.run(
        run_enrichment_worker(
            not headed, debug, effective_campaign, workers=final_workers
        )
    )
