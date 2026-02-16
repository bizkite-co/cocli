import csv
import socket
import time
import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from playwright.async_api import async_playwright

from ..core.queue.factory import get_queue_manager
from ..scrapers.google_maps import scrape_google_maps
from ..scrapers.google_maps_details import scrape_google_maps_details
from ..models.scrape_task import ScrapeTask
from ..models.google_maps_prospect import GoogleMapsProspect
from ..models.google_maps_list_item import GoogleMapsListItem
from ..models.gm_item_task import GmItemTask
from ..models.queue import QueueMessage
from ..core.prospects_csv_manager import ProspectsIndexManager
from ..core.config import load_campaign_config, get_campaign_dir
from ..utils.playwright_utils import setup_optimized_context
from ..utils.headers import ANTI_BOT_HEADERS, USER_AGENT
from ..core.text_utils import slugify
from ..core.utils import UNIT_SEP

logger = logging.getLogger(__name__)

class WorkerService:
    def __init__(self, campaign_name: str, processed_by: Optional[str] = None):
        self.campaign_name = campaign_name
        self.processed_by = processed_by or (os.getenv("COCLI_HOSTNAME") or socket.gethostname().split(".")[0])
        self.config = load_campaign_config(campaign_name)
        self.aws_config = self.config.get("aws", {})
        self.bucket_name = (
            self.aws_config.get("data_bucket_name") 
            or self.aws_config.get("cocli_data_bucket_name") 
            or f"cocli-data-{campaign_name}"
        )
        
    def get_s3_client(self) -> Any:
        from ..core.reporting import get_boto3_session
        session = get_boto3_session(self.config)
        return session.client("s3")

    async def _run_scrape_task_loop(
        self,
        browser_or_context: Any,
        scrape_queue: Any,
        gm_list_item_queue: Any,
        s3_client: Any,
        debug: bool,
        tracker: Optional[Any] = None,
    ) -> None:
        while True:
            connected = True
            if hasattr(browser_or_context, "is_connected"):
                connected = browser_or_context.is_connected()
            elif hasattr(browser_or_context, "browser") and browser_or_context.browser:
                connected = browser_or_context.browser.is_connected()

            if not connected:
                logger.error("Browser is disconnected. Breaking task loop to restart.")
                break

            tasks: List[ScrapeTask] = await asyncio.to_thread(scrape_queue.poll, batch_size=1)
            if not tasks:
                await asyncio.sleep(5)
                continue

            task = tasks[0]
            grid_tiles = None
            if task.tile_id:
                logger.info(f"Grid Task ({task.tile_id}): {task.search_phrase}")
                grid_tiles = [
                    {
                        "id": task.tile_id, 
                        "center_lat": task.latitude, 
                        "center_lon": task.longitude, 
                        "center": {"lat": task.latitude, "lon": task.longitude}
                    }
                ]
            else:
                logger.info(f"Point Task: {task.search_phrase} @ {task.latitude}, {task.longitude}")

            start_mb = tracker.get_mb() if tracker else 0.0

            try:
                location_param = {"latitude": str(task.latitude), "longitude": str(task.longitude)}
                prospect_count = 0
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
                    discovered_items: List[GoogleMapsListItem] = []
                    async with asyncio.timeout(900):
                        async for list_item in scrape_google_maps(
                            browser=browser_or_context,
                            location_param=location_param,
                            search_strings=[task.search_phrase],
                            campaign_name=task.campaign_name,
                            grid_tiles=grid_tiles,
                            debug=debug,
                            s3_client=s3_client,
                            s3_bucket=self.bucket_name,
                            processed_by=self.processed_by,
                        ):
                            if not list_item.place_id:
                                continue
                            prospect_count += 1
                            discovered_items.append(list_item)
                            details_task = list_item.to_task(task.campaign_name, force_refresh=False)
                            gm_list_item_queue.push(details_task)

                            # DISCOVERY LINKAGE: Create/Update the hollow company record immediately
                            try:
                                from ..models.company import Company
                                company_obj = Company.get(list_item.company_slug)
                                if not company_obj:
                                    company_obj = Company(
                                        name=list_item.name or list_item.company_slug,
                                        slug=list_item.company_slug,
                                        tags=[task.campaign_name, task.search_phrase]
                                    )
                                
                                # Merge identifiers
                                if not company_obj.place_id:
                                    company_obj.place_id = list_item.place_id
                                
                                if company_obj.latitude is None and task.latitude:
                                    company_obj.latitude = task.latitude
                                
                                if company_obj.longitude is None and task.longitude:
                                    company_obj.longitude = task.longitude
                                
                                if task.campaign_name not in company_obj.tags:
                                    company_obj.tags.append(task.campaign_name)
                                
                                if task.search_phrase not in company_obj.tags:
                                    company_obj.tags.append(task.search_phrase)
                                    
                                company_obj.save(email_sync=False)
                            except Exception as e:
                                logger.error(f"Failed to create discovery linkage for {list_item.company_slug}: {e}")
                    
                    if discovered_items:
                        try:
                            from ..core.paths import paths
                            from ..core.sharding import get_geo_shard, get_grid_tile_id
                            shard = get_geo_shard(task.latitude)
                            
                            # Standardized 0.1 degree tile ID
                            tile_id = task.tile_id
                            if not tile_id:
                                tile_id = get_grid_tile_id(task.latitude, task.longitude)
                            
                            # Clean ID for path construction (removes any phrase suffix if present in task.tile_id)
                            # Actually, we want the path to be {shard}/{tile_id}/{phrase}.usv
                            base_tile = tile_id.split("_")[0] + "_" + tile_id.split("_")[1]
                            
                            local_results_dir = paths.queue(task.campaign_name, "gm-list") / "completed" / "results" / shard / base_tile
                            local_results_dir.mkdir(parents=True, exist_ok=True)
                            
                            phrase_slug = slugify(task.search_phrase)
                            result_file = local_results_dir / f"{phrase_slug}.usv"
                            
                            with open(result_file, "w") as rf:
                                for item in discovered_items:
                                    rf.write(f"{item.place_id}{UNIT_SEP}{item.company_slug}{UNIT_SEP}{item.name}{UNIT_SEP}{item.phone or ''}\n")
                            
                            s3_key = f"campaigns/{task.campaign_name}/queues/gm-list/completed/results/{shard}/{base_tile}/{phrase_slug}.usv"
                            s3_client.upload_file(str(result_file), self.bucket_name, s3_key)
                        except Exception as res_err:
                            logger.warning(f"Failed to write batch result log: {res_err}")
                finally:
                    if heartbeat_task:
                        heartbeat_task.cancel()
                        try:
                            await asyncio.wait_for(heartbeat_task, timeout=2)
                        except Exception:
                            pass

                if tracker:
                    logger.info(f"Task Complete. Found {prospect_count} prospects. Bandwidth: {tracker.get_mb() - start_mb:.2f} MB")
                else:
                    logger.info(f"Task Complete. Found {prospect_count} prospects.")
                scrape_queue.ack(task)
            except Exception as e:
                logger.error(f"Task Failed: {e}")
                scrape_queue.nack(task)
                if "Target page, context or browser has been closed" in str(e) or not connected:
                    break

    async def _run_details_task_loop(
        self,
        browser_or_context: Any,
        gm_list_item_queue: Any,
        enrichment_queue: Any,
        s3_client: Any,
        debug: bool,
        once: bool,
        tracker: Optional[Any] = None,
    ) -> None:
        while True:
            connected = True
            if hasattr(browser_or_context, "is_connected"):
                connected = browser_or_context.is_connected()
            elif hasattr(browser_or_context, "browser") and browser_or_context.browser:
                connected = browser_or_context.browser.is_connected()

            if not connected:
                logger.error("Browser is disconnected. Restarting.")
                break

            tasks: List[GmItemTask] = await asyncio.to_thread(gm_list_item_queue.poll, batch_size=1)
            if not tasks:
                if once:
                    return
                await asyncio.sleep(5)
                continue

            task = tasks[0]
            logger.info(f"Detail Task found: {task.place_id}")
            start_mb = tracker.get_mb() if tracker else 0.0

            try:
                csv_manager = ProspectsIndexManager(task.campaign_name)
                file_path = csv_manager.get_file_path(task.place_id)
                rel_path = file_path.relative_to(csv_manager.index_dir)
                s3_key = f"campaigns/{task.campaign_name}/indexes/google_maps_prospects/{rel_path}"

                if not file_path.exists():
                    try:
                        s3_client.download_file(self.bucket_name, s3_key, str(file_path))
                    except Exception:
                        pass

                existing_prospect = None
                if file_path.exists():
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            reader = csv.DictReader(f)
                            existing_data = next(reader, None)
                            if existing_data:
                                existing_prospect = GoogleMapsProspect.model_validate(existing_data)
                    except Exception as e:
                        logger.warning(f"Error reading local file {file_path}: {e}")

                if existing_prospect and not task.force_refresh:
                    if existing_prospect.updated_at:
                        u_at = existing_prospect.updated_at
                        if isinstance(u_at, str):
                            try:
                                u_at = datetime.fromisoformat(u_at)
                            except Exception:
                                u_at = None
                        if u_at:
                            if u_at.tzinfo is not None:
                                u_at = u_at.replace(tzinfo=None)
                            age_days = (datetime.now() - u_at).total_seconds() / 86400
                            if age_days < 30:
                                logger.info(f"Skipping scrape for {task.place_id}. Data is fresh.")
                                if existing_prospect.domain and existing_prospect.name:
                                    enrichment_queue.push(QueueMessage(
                                        domain=existing_prospect.domain, 
                                        company_slug=slugify(existing_prospect.name), 
                                        campaign_name=task.campaign_name, 
                                        force_refresh=task.force_refresh, 
                                        ack_token=None
                                    ))
                                gm_list_item_queue.ack(task)
                                if once:
                                    return
                                continue

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
                            page=page, place_id=task.place_id, campaign_name=task.campaign_name,
                            name=getattr(task, "name", None), company_slug=getattr(task, "company_slug", None),
                            debug=debug
                        )
                    finally:
                        await page.close()
                finally:
                    if heartbeat_task:
                        heartbeat_task.cancel()
                        try:
                            await asyncio.wait_for(heartbeat_task, timeout=2)
                        except Exception:
                            pass

                if not detailed_prospect_data:
                    gm_list_item_queue.nack(task)
                    if once:
                        return
                    continue

                detailed_prospect_data.processed_by = self.processed_by
                detailed_prospect_data.discovery_phrase = task.discovery_phrase
                detailed_prospect_data.discovery_tile_id = task.discovery_tile_id
                final_prospect_data = detailed_prospect_data
                if existing_prospect:
                    merged_data = existing_prospect.model_dump()
                    new_data = detailed_prospect_data.model_dump(exclude_unset=True)
                    merged_data.update({k: v for k, v in new_data.items() if v is not None})
                    final_prospect_data = GoogleMapsProspect.model_validate(merged_data)

                final_prospect_data.processed_by = self.processed_by
                final_prospect_data.updated_at = datetime.now()

                if csv_manager.append_prospect(final_prospect_data):
                    try:
                        s3_client.upload_file(str(file_path), self.bucket_name, s3_key)
                    except Exception as e:
                        logger.error(f"S3 Upload Error: {e}")
                    
                    # LINKAGE: Create/Update the company record immediately
                    try:
                        from ..models.company import Company
                        company_obj = Company.get(final_prospect_data.company_slug)
                        if not company_obj:
                            company_obj = Company(
                                name=final_prospect_data.name or final_prospect_data.company_slug,
                                slug=final_prospect_data.company_slug,
                                tags=[task.campaign_name]
                            )
                        
                        # Merge identifiers
                        if not company_obj.place_id:
                            company_obj.place_id = final_prospect_data.place_id
                        
                        if company_obj.latitude is None and final_prospect_data.latitude:
                            company_obj.latitude = final_prospect_data.latitude
                        
                        if company_obj.longitude is None and final_prospect_data.longitude:
                            company_obj.longitude = final_prospect_data.longitude
                        
                        if task.campaign_name not in company_obj.tags:
                            company_obj.tags.append(task.campaign_name)
                        
                        if final_prospect_data.keyword and final_prospect_data.keyword not in company_obj.tags:
                            company_obj.tags.append(final_prospect_data.keyword)
                            
                        # Save identity baseline
                        company_obj.save(email_sync=False)
                    except Exception as e:
                        logger.error(f"Failed to create company linkage for {final_prospect_data.company_slug}: {e}")

                if final_prospect_data.domain and final_prospect_data.name:
                    enrichment_queue.push(QueueMessage(
                        domain=final_prospect_data.domain, 
                        company_slug=slugify(final_prospect_data.name), 
                        campaign_name=task.campaign_name, 
                        force_refresh=task.force_refresh, 
                        ack_token=None
                    ))

                if hasattr(final_prospect_data, "email") and final_prospect_data.email:
                    try:
                        from ..core.email_index_manager import EmailIndexManager
                        from ..models.email import EmailEntry
                        email_manager = EmailIndexManager(task.campaign_name)
                        entry = EmailEntry(
                            email=final_prospect_data.email, 
                            domain=final_prospect_data.domain or final_prospect_data.email.split("@")[-1], 
                            company_slug=final_prospect_data.company_slug, 
                            source="gmb_details_worker", 
                            tags=[task.campaign_name]
                        )
                        email_manager.add_email(entry)
                    except Exception:
                        pass

                if tracker:
                    logger.info(f"Detailing Complete for {task.place_id}. Bandwidth: {tracker.get_mb() - start_mb:.2f} MB")
                else:
                    logger.info(f"Detailing Complete for {task.place_id}.")
                gm_list_item_queue.ack(task)
                if once:
                    return
            except Exception as e:
                logger.error(f"Detail Task Failed for {task.place_id}: {e}")
                gm_list_item_queue.nack(task)
                if once:
                    return
                if "Target page, context or browser has been closed" in str(e) or not connected:
                    break

    async def run_details_worker(
        self,
        headless: bool,
        debug: bool,
        once: bool = False,
        workers: int = 1,
    ) -> None:
        async with async_playwright() as p:
            while True:
                browser = await p.chromium.launch(
                    headless=headless,
                    args=[
                        "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
                        "--disable-accelerated-2d-canvas", "--no-first-run", "--no-zygote",
                        "--disable-gpu", "--disable-software-rasterizer",
                    ],
                )
                context = await browser.new_context(
                    ignore_https_errors=True, user_agent=USER_AGENT, extra_http_headers=ANTI_BOT_HEADERS,
                )
                tracker = await setup_optimized_context(context)
                
                s3_client = self.get_s3_client()
                gm_list_item_queue = get_queue_manager("details", use_cloud=True, queue_type="gm_list_item", campaign_name=self.campaign_name, s3_client=s3_client)
                enrichment_queue = get_queue_manager("enrichment", use_cloud=True, queue_type="enrichment", campaign_name=self.campaign_name, s3_client=s3_client)

                tasks = [
                    self._run_details_task_loop(context, gm_list_item_queue, enrichment_queue, s3_client, debug, once, tracker=tracker)
                    for _ in range(workers)
                ]
                await asyncio.gather(*tasks)
                await browser.close()
                if once:
                    break
                await asyncio.sleep(5)

    async def run_worker(
        self,
        headless: bool,
        debug: bool,
        workers: int = 1,
    ) -> None:
        async with async_playwright() as p:
            while True:
                browser = await p.chromium.launch(
                    headless=headless,
                    args=[
                        "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
                        "--disable-accelerated-2d-canvas", "--no-first-run", "--no-zygote",
                        "--disable-gpu", "--disable-software-rasterizer",
                    ],
                )
                context = await browser.new_context(
                    ignore_https_errors=True, user_agent=USER_AGENT, extra_http_headers=ANTI_BOT_HEADERS,
                )
                tracker = await setup_optimized_context(context)
                
                s3_client = self.get_s3_client()
                scrape_queue = get_queue_manager("scrape_tasks", use_cloud=True, queue_type="scrape", campaign_name=self.campaign_name)
                gm_list_item_queue = get_queue_manager("gm_list_item", use_cloud=True, queue_type="gm_list_item", campaign_name=self.campaign_name)

                tasks = [
                    self._run_scrape_task_loop(context, scrape_queue, gm_list_item_queue, s3_client, debug, tracker=tracker)
                    for _ in range(workers)
                ]
                await asyncio.gather(*tasks)
                await browser.close()
                await asyncio.sleep(5)

    async def run_enrichment_worker(
        self,
        headless: bool,
        debug: bool,
        workers: int = 1,
    ) -> None:
        async with async_playwright() as p:
            while True:
                browser = await p.chromium.launch(
                    headless=headless,
                    args=["--no-sandbox"]
                )
                context = await browser.new_context(
                    ignore_https_errors=True, user_agent=USER_AGENT, extra_http_headers=ANTI_BOT_HEADERS,
                )
                tracker = await setup_optimized_context(context)
                
                s3_client = self.get_s3_client()
                enrichment_queue = get_queue_manager("enrichment", use_cloud=True, queue_type="enrichment", campaign_name=self.campaign_name)

                tasks = [
                    self._run_enrichment_task_loop(context, enrichment_queue, debug, False, s3_client=s3_client, tracker=tracker)
                    for _ in range(workers)
                ]
                await asyncio.gather(*tasks)
                await browser.close()
                await asyncio.sleep(5)

    async def _run_enrichment_task_loop(
        self,
        browser_or_context: Any,
        enrichment_queue: Any,
        debug: bool,
        once: bool,
        s3_client: Optional[Any] = None,
        tracker: Optional[Any] = None,
    ) -> None:
        from ..core.enrichment import enrich_company_website
        from ..models.company import Company
        from ..models.campaign import Campaign
        from ..core.s3_company_manager import S3CompanyManager

        try:
            campaign_obj = Campaign.load(self.campaign_name)
        except Exception as e:
            logger.error(f"Could not load Campaign '{self.campaign_name}': {e}")
            if once:
                return
            await asyncio.sleep(10)
            return

        s3_company_manager = None
        if s3_client:
            try:
                s3_company_manager = S3CompanyManager(campaign=campaign_obj)
                s3_company_manager.s3_client = s3_client
                s3_company_manager.s3_bucket_name = self.bucket_name
            except Exception:
                pass

        while True:
            connected = True
            if hasattr(browser_or_context, "is_connected"):
                connected = browser_or_context.is_connected()
            elif hasattr(browser_or_context, "browser") and browser_or_context.browser:
                connected = browser_or_context.browser.is_connected()

            if not connected:
                logger.error("Browser is disconnected. Breaking task loop to restart.")
                break

            tasks: List[QueueMessage] = await asyncio.to_thread(enrichment_queue.poll, batch_size=1)
            if not tasks:
                if once:
                    return
                await asyncio.sleep(5)
                continue

            task = tasks[0]
            logger.info(f"Enrichment Task found: {task.domain}")
            start_mb = tracker.get_mb() if tracker else 0.0

            try:
                company = Company.get(task.company_slug)
                if not company and s3_company_manager:
                    company = await s3_company_manager.fetch_company_index(task.company_slug)
                    if company:
                        company.save()
                if not company:
                    company = Company(name=task.company_slug, domain=task.domain, slug=task.company_slug)

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
                    website_data = await asyncio.wait_for(
                        enrich_company_website(
                            browser=browser_or_context, 
                            company=company, 
                            campaign=campaign_obj, 
                            force=task.force_refresh, 
                            debug=debug
                        ),
                        timeout=300
                    )
                except asyncio.TimeoutError:
                    logger.error(f"WATCHDOG: Enrichment for {task.domain} timed out.")
                    website_data = None
                finally:
                    if heartbeat_task:
                        heartbeat_task.cancel()
                        try:
                            await asyncio.wait_for(heartbeat_task, timeout=2)
                        except Exception:
                            pass

                if website_data:
                    website_data.processed_by = self.processed_by
                    website_data.save(task.company_slug)
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
                    for platform in ["facebook", "linkedin", "instagram", "twitter", "youtube"]:
                        attr = f"{platform}_url"
                        new_val = getattr(website_data, attr)
                        if new_val and not getattr(company, attr):
                            setattr(company, attr, new_val)
                    company.processed_by = self.processed_by
                    company.save()
                    if s3_company_manager:
                        await s3_company_manager.save_company_index(company)
                        await s3_company_manager.save_website_enrichment(task.company_slug, website_data)
                    if tracker:
                        logger.info(f"Enrichment Complete for {task.domain}. Bandwidth: {tracker.get_mb() - start_mb:.2f} MB")
                    else:
                        logger.info(f"Enrichment Complete for {task.domain}.")
                    enrichment_queue.ack(task)
                else:
                    enrichment_queue.ack(task)
                if once:
                    return
            except Exception as e:
                logger.error(f"Enrichment Task Failed for {task.domain}: {e}")
                enrichment_queue.nack(task)
                await asyncio.sleep(5)
                if once:
                    return
                if "Target page, context or browser has been closed" in str(e) or not connected:
                    break

    async def run_supervisor(self, headless: bool, debug: bool, interval: int) -> None:
        """Starts a supervisor that dynamically manages scrape and details workers."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless,
                args=[
                    "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
                    "--disable-accelerated-2d-canvas", "--no-first-run", "--no-zygote",
                    "--disable-gpu", "--disable-software-rasterizer",
                ],
            )
            scrape_tasks: Dict[int, asyncio.Task[Any]] = {}
            details_tasks: Dict[int, asyncio.Task[Any]] = {}
            enrichment_tasks: Dict[int, asyncio.Task[Any]] = {}
            command_task: Optional[asyncio.Task[Any]] = None

            context = await browser.new_context(
                ignore_https_errors=True, user_agent=USER_AGENT, extra_http_headers=ANTI_BOT_HEADERS,
            )
            await setup_optimized_context(context)

            from ..utils.smart_sync_up import run_smart_sync_up
            last_sync_time = last_report_time = time.time()
            last_heartbeat_time = last_client_refresh = 0.0
            
            s3_client = command_queue = scrape_queue = gm_list_item_queue = enrichment_queue = None

            while True:
                try:
                    # 0. Sync config from S3 (Efficient Targeted Sync)
                    from ..services.sync_service import SyncService
                    try:
                        sync_service = SyncService(self.campaign_name)
                        await asyncio.to_thread(sync_service.sync_config, direction="down")
                    except Exception as e:
                        logger.warning(f"Failed to sync config from S3: {e}")

                    now = time.time()
                    if s3_client is None or now - last_client_refresh > 1800:
                        s3_client = self.get_s3_client()
                        scrape_queue = get_queue_manager("scrape", use_cloud=True, queue_type="scrape", campaign_name=self.campaign_name, s3_client=s3_client)
                        gm_list_item_queue = get_queue_manager("details", use_cloud=True, queue_type="gm_list_item", campaign_name=self.campaign_name, s3_client=s3_client)
                        enrichment_queue = get_queue_manager("enrichment", use_cloud=True, queue_type="enrichment", campaign_name=self.campaign_name, s3_client=s3_client)
                        command_queue = get_queue_manager("command", use_cloud=True, queue_type="command", campaign_name=self.campaign_name)
                        last_client_refresh = now

                    if now - last_heartbeat_time > 60:
                        await self._push_supervisor_heartbeat(s3_client, scrape_tasks, details_tasks, enrichment_tasks)
                        last_heartbeat_time = now

                    if command_task is None or command_task.done():
                        command_task = asyncio.create_task(self._run_command_poller_loop(command_queue, s3_client))
                    
                    config = load_campaign_config(self.campaign_name)
                    scaling = config.get("prospecting", {}).get("scaling", {}).get(self.processed_by, {})
                    target_scrape = scaling.get("gm-list", scaling.get("scrape", 0))
                    target_details = scaling.get("gm-details", scaling.get("details", 0))
                    target_enrich = scaling.get("enrichment", 0)

                    while len(scrape_tasks) < target_scrape:
                        new_id = len(scrape_tasks)
                        scrape_tasks[new_id] = asyncio.create_task(self._run_scrape_task_loop(browser, scrape_queue, gm_list_item_queue, s3_client, debug))
                    while len(scrape_tasks) > target_scrape:
                        old_id = max(scrape_tasks.keys())
                        scrape_tasks[old_id].cancel()
                        del scrape_tasks[old_id]

                    while len(details_tasks) < target_details:
                        new_id = len(details_tasks)
                        details_tasks[new_id] = asyncio.create_task(self._run_details_task_loop(browser, gm_list_item_queue, enrichment_queue, s3_client, debug, False))
                    while len(details_tasks) > target_details:
                        old_id = max(details_tasks.keys())
                        details_tasks[old_id].cancel()
                        del details_tasks[old_id]

                    # 4. Adjust Enrichment Tasks
                    while len(enrichment_tasks) < target_enrich:
                        new_id = len(enrichment_tasks)
                        logger.info(f"Scaling UP: Starting Enrichment Task {new_id}")
                        
                        # TASK WRAPPER: Create fresh context for every single task to prevent memory leaks
                        async def _run_single_enrichment_task() -> bool:
                            # Shared context from supervisor might leak, create a fresh one
                            # ignore_https_errors is important for broad scraping
                            tmp_context = await browser.new_context(
                                ignore_https_errors=True,
                                user_agent=USER_AGENT,
                                extra_http_headers=ANTI_BOT_HEADERS,
                            )
                            tmp_tracker = await setup_optimized_context(tmp_context)
                            found_task = False
                            try:
                                # Modify _run_enrichment_task_loop to return if it found a task
                                # For now, we'll just check if it returns quickly
                                start = time.time()
                                await self._run_enrichment_task_loop(
                                    tmp_context,
                                    enrichment_queue,
                                    debug,
                                    True, # once=True: Finish after one task
                                    s3_client=s3_client,
                                    tracker=tmp_tracker,
                                )
                                # If it took more than a second, it probably processed something
                                if time.time() - start > 1.0:
                                    found_task = True
                            finally:
                                await tmp_context.close()
                            return found_task

                        # Start as a persistent loop that restarts the wrapper
                        async def _persistent_enrichment_loop() -> None:
                            while True:
                                try:
                                    processed = await _run_single_enrichment_task()
                                    if not processed:
                                        await asyncio.sleep(10) # Heavy breather when queue empty
                                    else:
                                        await asyncio.sleep(1) # Small breather between tasks
                                except Exception as e:
                                    logger.error(f"Enrichment task wrapper error: {e}")
                                    await asyncio.sleep(10)

                        task = asyncio.create_task(_persistent_enrichment_loop())
                        enrichment_tasks[new_id] = task

                    while len(enrichment_tasks) > target_enrich:
                        old_id = max(enrichment_tasks.keys())
                        logger.info(f"Scaling DOWN: Stopping Enrichment Task {old_id}")
                        enrichment_tasks[old_id].cancel()
                        del enrichment_tasks[old_id]

                    if now - last_sync_time > 300:
                        campaign_dir = get_campaign_dir(self.campaign_name)
                        if campaign_dir:
                            await asyncio.to_thread(run_smart_sync_up, "indexes", self.bucket_name, f"campaigns/{self.campaign_name}/indexes/", campaign_dir / "indexes", self.campaign_name, self.aws_config, delete_remote=False)
                        last_sync_time = now

                    if now - last_report_time > 300:
                        from ..core.reporting import get_campaign_stats
                        stats = get_campaign_stats(self.campaign_name)
                        web_bucket = self.aws_config.get("cocli_web_bucket_name")
                        if web_bucket:
                            s3_client.put_object(Bucket=web_bucket, Key=f"reports/{self.campaign_name}.json", Body=json.dumps(stats, indent=2), ContentType="application/json")
                        last_report_time = now

                except Exception as e:
                    logger.error(f"Supervisor loop error: {e}")
                await asyncio.sleep(interval)

    async def _push_supervisor_heartbeat(self, s3_client: Any, scrape_tasks: Dict[int, asyncio.Task[Any]], details_tasks: Dict[int, asyncio.Task[Any]], enrichment_tasks: Dict[int, asyncio.Task[Any]]) -> None:
        try:
            import psutil
            from ..core.paths import paths
            stats = {
                "timestamp": datetime.now().isoformat(), "hostname": self.processed_by, "campaign": self.campaign_name,
                "version": "unknown", 
                "system": {"cpu_percent": psutil.cpu_percent(), "memory_percent": psutil.virtual_memory().percent, "memory_available_gb": round(psutil.virtual_memory().available / (1024**3), 2), "load_avg": list(os.getloadavg())},
                "workers": {"scrape": len(scrape_tasks), "details": len(details_tasks), "enrichment": len(enrichment_tasks)},
                "status": "healthy"
            }
            # USE self.bucket_name which is resolved in __init__ from campaign config
            s3_client.put_object(Bucket=self.bucket_name, Key=paths.s3_heartbeat(self.processed_by), Body=json.dumps(stats, indent=2), ContentType="application/json")
        except Exception as e:
            logger.error(f"HEARTBEAT CRITICAL FAILURE: {e}")

    async def get_cluster_health(self) -> List[Dict[str, Any]]:
        """
        Checks health of all Raspberry Pi workers defined in the campaign configuration.
        """
        import subprocess
        
        # 1. Resolve hosts from config
        scaling = self.config.get("prospecting", {}).get("scaling", {})
        cluster_config = self.config.get("cluster", {})
        
        # Nodes can be explicitly defined in [cluster.nodes] 
        # as a list of {"host": "...", "label": "..."}
        # Or we fall back to the keys in prospecting.scaling
        nodes = cluster_config.get("nodes", [])
        
        if not nodes:
            for host_key in scaling.keys():
                if host_key == "fargate":
                    continue
                # Default convention: host_key + .pi
                host = host_key if "." in host_key else f"{host_key}.pi"
                nodes.append({"host": host, "label": host_key.capitalize()})
        
        if not nodes:
            # Final fallback to a default if nothing is configured
            logger.warning(f"No workers configured for campaign {self.campaign_name}")
            return []

        results = []
        for node in nodes:
            host = node.get("host")
            label = node.get("label", host)
            if not host:
                continue
                
            try:
                # Combined command to save SSH overhead
                cmd = "uptime; vcgencmd measure_volts; vcgencmd get_throttled; docker ps --format '{{.Names}}|{{.Status}}'"
                res = await asyncio.to_thread(
                    subprocess.run,
                    ["ssh", "-o", "ConnectTimeout=3", f"mstouffer@{host}", cmd],
                    capture_output=True, text=True
                )
                
                host_info = {"host": host, "label": label, "online": res.returncode == 0}
                if res.returncode == 0:
                    lines = res.stdout.strip().split("\n")
                    host_info["uptime"] = lines[0] if len(lines) > 0 else "Unknown"
                    host_info["voltage"] = lines[1].replace("volt=", "") if len(lines) > 1 else "Unknown"
                    host_info["throttled"] = lines[2] if len(lines) > 2 else "Unknown"
                    host_info["containers"] = [line.split("|") for line in lines[3:] if "|" in line]
                else:
                    host_info["error"] = res.stderr.strip()
                results.append(host_info)
            except Exception as e:
                results.append({"host": host, "label": label, "online": False, "error": str(e)})
        return results

    async def _run_command_poller_loop(self, command_queue: Any, s3_client: Any) -> None:
        from ..application.campaign_service import CampaignService
        import shlex
        while True:
            try:
                campaign_service = CampaignService(self.campaign_name)
                commands = await asyncio.to_thread(command_queue.poll, batch_size=1)
                for cmd in commands:
                    logger.info(f"Executing remote command: {cmd.command}")
                    parts = shlex.split(cmd.command)
                    if "add-exclude" in cmd.command:
                        await asyncio.to_thread(campaign_service.add_exclude, parts[parts.index("add-exclude")+1])
                    elif "remove-exclude" in cmd.command:
                        await asyncio.to_thread(campaign_service.remove_exclude, parts[parts.index("remove-exclude")+1])
                    await asyncio.to_thread(command_queue.ack, cmd)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Command Poller error: {e}")
                await asyncio.sleep(10)
            await asyncio.sleep(5)
