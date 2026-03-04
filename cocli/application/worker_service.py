import socket
import time
import asyncio
import json
import logging
import os
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

from playwright.async_api import async_playwright

from ..core.queue.factory import get_queue_manager
from ..scrapers.google_maps import scrape_google_maps
from ..models.campaigns.queues.gm_list import ScrapeTask
from ..models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from ..models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem
from ..models.campaigns.queues.gm_details import GmItemTask
from ..models.campaigns.queues.base import QueueMessage
from ..core.prospects_csv_manager import ProspectsIndexManager
from ..core.config import load_campaign_config, get_campaign_dir
from ..utils.playwright_utils import setup_optimized_context
from ..utils.headers import ANTI_BOT_HEADERS, USER_AGENT
from ..core.text_utils import slugify

logger = logging.getLogger(__name__)

class WorkerService:
    def __init__(self, campaign_name: str, processed_by: Optional[str] = None, role: str = "full"):
        self.campaign_name = campaign_name
        self.processed_by = processed_by or (os.getenv("COCLI_HOSTNAME") or socket.gethostname().split(".")[0])
        self.role = role
        self.config = load_campaign_config(campaign_name)
        self.aws_config = self.config.get("aws", {})
        self.bucket_name = (
            self.aws_config.get("data_bucket_name") 
            or self.aws_config.get("cocli_data_bucket_name") 
            or f"cocli-data-{campaign_name}"
        )
        
    def get_s3_client(self) -> Any:
        from ..core.reporting import get_boto3_session
        profile = f"{self.campaign_name}-iot"
        session = get_boto3_session(self.config, profile_name=profile)
        return session.client("s3")

    async def _run_scrape_task_loop(
        self,
        browser: Any,
        scrape_queue: Any,
        gm_list_item_queue: Any,
        s3_client: Any,
        debug: bool,
        once: bool,
        headless: bool = True,
        workers: int = 1,
    ) -> None:
        while True:
            try:
                if not browser.is_connected():
                    logger.error("Browser is disconnected. Breaking task loop to restart.")
                    break
            except Exception as e:
                logger.error(f"Browser check failed: {e}")
                break

            tasks: List[ScrapeTask] = await asyncio.to_thread(scrape_queue.poll, batch_size=1)
            if not tasks:
                if once:
                    return
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
                            browser=browser,
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
                                from ..models.companies.company import Company
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
                            # Use the Modular Processor
                            from .processors.gm_list import GmListProcessor
                            from ..utils.headers import USER_AGENT, ANTI_BOT_HEADERS
                            
                            metadata = {
                                "user_agent": USER_AGENT,
                                "common_headers": ANTI_BOT_HEADERS,
                                "browser_settings": {
                                    "headless": headless,
                                    "workers": workers,
                                    "viewport": {"width": 2000, "height": 2000},
                                    "version": "1.1.0"
                                },
                                "timestamp": datetime.now(UTC).isoformat()
                            }
                            
                            processor = GmListProcessor(processed_by=self.processed_by, bucket_name=self.bucket_name)
                            await processor.process_results(task, discovered_items, s3_client=s3_client, metadata=metadata)
                        except Exception as res_err:
                            logger.warning(f"Failed to write batch result log: {res_err}")
                finally:
                    if heartbeat_task:
                        heartbeat_task.cancel()
                        try:
                            await asyncio.wait_for(heartbeat_task, timeout=2)
                        except Exception:
                            pass

                logger.info(f"Task Complete. Found {prospect_count} prospects.")
                
                # Capture result count for the receipt
                task.result_count = len(discovered_items)
                scrape_queue.ack(task)
                
                if once:
                    return
            except Exception as e:
                logger.error(f"Task Failed: {e}")
                scrape_queue.nack(task)
                if "Target page, context or browser has been closed" in str(e):
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
                
                # Use OMAP-compliant S3 key for WAL records
                from ..core.sharding import get_place_id_shard
                shard = get_place_id_shard(task.place_id)
                s3_key = f"campaigns/{task.campaign_name}/indexes/google_maps_prospects/wal/{shard}/{task.place_id}.usv"

                if not file_path.exists():
                    try:
                        s3_client.download_file(self.bucket_name, s3_key, str(file_path))
                    except Exception:
                        pass

                existing_prospect = None
                if file_path.exists():
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            for line in f:
                                if not line.strip():
                                    continue
                                # Robust header detection: skip if it looks like the header from ScrapeIndex
                                if "created_at" in line or "scrape_date" in line:
                                    continue
                                try:
                                    existing_prospect = GoogleMapsProspect.from_usv(line)
                                    break # Only one prospect per file in details WAL
                                except Exception as e:
                                    logger.warning(f"Error parsing line in {file_path}: {e}")
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
                        if self.role == "scraper":
                            # SCRAPER ROLE: Just capture raw HTML witness
                            from ..scrapers.google_maps_details import capture_google_maps_raw
                            witness = await capture_google_maps_raw(
                                page=page, 
                                place_id=task.place_id, 
                                campaign_name=task.campaign_name,
                                processed_by=self.processed_by,
                                debug=debug
                            )
                            if witness:
                                # MANDATE: Save to raw/gm-details/
                                from ..core.paths import paths
                                from ..core.sharding import get_place_id_shard
                                shard = get_place_id_shard(task.place_id)
                                
                                # Local Save
                                local_dir = paths.campaign(task.campaign_name).path / "raw" / "gm-details" / shard / task.place_id
                                local_dir.mkdir(parents=True, exist_ok=True)
                                
                                with open(local_dir / "witness.html", "w", encoding="utf-8") as f:
                                    f.write(witness.html)
                                with open(local_dir / "metadata.json", "w", encoding="utf-8") as f:
                                    f.write(json.dumps(witness.metadata, indent=2))
                                
                                # S3 Mirror
                                if s3_client and self.bucket_name:
                                    s3_prefix = f"campaigns/{task.campaign_name}/raw/gm-details/{shard}/{task.place_id}"
                                    s3_client.upload_file(str(local_dir / "witness.html"), self.bucket_name, f"{s3_prefix}/witness.html")
                                    s3_client.upload_file(str(local_dir / "metadata.json"), self.bucket_name, f"{s3_prefix}/metadata.json")

                                logger.info(f"Witness saved to raw/gm-details for {task.place_id}")
                                scrape_success = True
                            else:
                                scrape_success = False
                        else:
                            # FULL or other roles: Use the Modular Processor
                            from .processors.google_maps import GoogleMapsDetailsProcessor
                            processor = GoogleMapsDetailsProcessor(processed_by=self.processed_by)
                            final_prospect_data = await processor.process(task, page, debug=debug)
                            scrape_success = final_prospect_data is not None
                    finally:
                        await page.close()
                finally:
                    if heartbeat_task:
                        heartbeat_task.cancel()
                        try:
                            await asyncio.wait_for(heartbeat_task, timeout=2)
                        except Exception:
                            pass

                if not scrape_success and self.role != "processor":
                    gm_list_item_queue.nack(task)
                    if once:
                        return
                    continue

                gm_list_item_queue.ack(task)
                
                if once:
                    return

                if self.role == "scraper":
                    continue

                # LINKAGE (Only for Full/Processor roles)
                if final_prospect_data:
                    if final_prospect_data.domain and final_prospect_data.name:
                        enrichment_queue.push(QueueMessage(
                            domain=str(final_prospect_data.domain), 
                            company_slug=slugify(final_prospect_data.name), 
                            campaign_name=task.campaign_name, 
                            force_refresh=task.force_refresh, 
                            ack_token=None
                        ))

                    if hasattr(final_prospect_data, "email") and final_prospect_data.email:
                        try:
                            from ..core.email_index_manager import EmailIndexManager
                            from ..models.campaigns.indexes.email import EmailEntry
                            email_manager = EmailIndexManager(task.campaign_name)
                            entry = EmailEntry(
                                email=str(final_prospect_data.email), 
                                domain=str(final_prospect_data.domain or final_prospect_data.email.split("@")[-1]), 
                                company_slug=str(final_prospect_data.company_slug), 
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

    async def run_orchestrated_workers(self, worker_definitions: List[Any], headless: bool = True, debug: bool = False) -> None:
        """
        Launches and manages multiple named worker instances as defined in the orchestration config.
        """
        logger.info(f"Launching {len(worker_definitions)} orchestrated workers on {self.processed_by}...")
        
        # Start the Gossip Bridge for real-time cluster coordination
        from ..core.gossip_bridge import bridge
        if bridge:
            try:
                bridge.start()
                logger.info("Gossip Bridge started.")
            except Exception as e:
                logger.warning(f"Gossip Bridge failed to start: {e}")

        tasks = []
        for wd in worker_definitions:
            logger.info(f"Starting Orchestrated Worker: {wd.name} (Role: {wd.role}, Type: {wd.content_type}, Count: {wd.workers})")
            
            # Create a specialized service instance for this worker's role
            worker_service = WorkerService(
                campaign_name=self.campaign_name, 
                role=wd.role, 
                processed_by=f"{self.processed_by}-{wd.name}"
            )
            
            if wd.content_type == "gm-list":
                coro = worker_service.run_discovery_worker(
                    headless=headless, 
                    debug=debug, 
                    once=False, 
                    workers=wd.workers
                )
            elif wd.content_type == "gm-details":
                coro = worker_service.run_details_worker(
                    headless=headless, 
                    debug=debug, 
                    once=False, 
                    workers=wd.workers,
                    role=wd.role
                )
            elif wd.content_type == "enrichment":
                coro = worker_service.run_enrichment_worker(
                    headless=headless,
                    debug=debug,
                    workers=wd.workers,
                    role=wd.role
                )
            else:
                logger.error(f"Unknown content type for worker {wd.name}: {wd.content_type}")
                continue
                
            tasks.append(asyncio.create_task(coro))

        if not tasks:
            logger.warning("No valid worker tasks to run.")
            return

        # Wait for all workers (they run indefinitely unless cancelled)
        await asyncio.gather(*tasks)

    async def run_discovery_worker(self, headless: bool = True, debug: bool = False, once: bool = False, workers: int = 1) -> None:
        """Explicit alias for GM-List discovery worker."""
        await self.run_worker(headless=headless, debug=debug, once=once, workers=workers, role="full")

    async def run_details_worker(
        self,
        headless: bool,
        debug: bool,
        once: bool = False,
        workers: int = 1,
        role: str = "full"
    ) -> None:
        # Ensure our role is set correctly for this run
        self.role = role
        if role == "processor":
            # Processor role doesn't need a browser
            s3_client = self.get_s3_client()
            # USE LOCAL QUEUE for local recovery verification
            gm_list_item_queue = get_queue_manager("details", use_cloud=False, queue_type="gm_list_item", campaign_name=self.campaign_name, s3_client=s3_client)
            enrichment_queue = get_queue_manager("enrichment", use_cloud=False, queue_type="enrichment", campaign_name=self.campaign_name, s3_client=s3_client)
            
            logger.info("Starting GM Details PROCESSOR (No Browser)")
            tasks = [
                self._run_details_processor_loop(gm_list_item_queue, enrichment_queue, s3_client, debug, once)
                for _ in range(workers)
            ]
            await asyncio.gather(*tasks)
            return

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
                
                try:
                    s3_client = self.get_s3_client()
                    use_cloud = True
                except Exception as e:
                    logger.warning(f"Could not initialize S3 client: {e}. Falling back to LOCAL-ONLY mode.")
                    s3_client = None
                    use_cloud = False

                gm_list_item_queue = get_queue_manager("details", use_cloud=use_cloud, queue_type="gm_list_item", campaign_name=self.campaign_name, s3_client=s3_client)
                enrichment_queue = get_queue_manager("enrichment", use_cloud=use_cloud, queue_type="enrichment", campaign_name=self.campaign_name, s3_client=s3_client)

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
        once: bool = False,
        workers: int = 1,
        role: str = "full"
    ) -> None:
        """
        Main worker loop for GM List (Discovery).
        """
        self.role = role
        logger.info(f"Starting GM List Worker (Role: {self.role}) on node {self.processed_by} for campaign {self.campaign_name}...")
        
        if role == "processor":
            logger.info("Starting GM List PROCESSOR (No Browser)")
            # Processor role for GM List is currently a no-op as scraper handles results
            return

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

                try:
                    s3_client = self.get_s3_client()
                    use_cloud = True
                except Exception as e:
                    logger.warning(f"Could not initialize S3 client: {e}. Falling back to LOCAL-ONLY mode.")
                    s3_client = None
                    use_cloud = False

                # We use local queue if cloud fails
                scrape_queue = get_queue_manager("scrape", use_cloud=use_cloud, queue_type="scrape", campaign_name=self.campaign_name, s3_client=s3_client)
                gm_list_item_queue = get_queue_manager("details", use_cloud=use_cloud, queue_type="gm_list_item", campaign_name=self.campaign_name, s3_client=s3_client)

                tasks = [
                    self._run_scrape_task_loop(browser, scrape_queue, gm_list_item_queue, s3_client, debug, once, headless=headless, workers=workers)
                    for _ in range(workers)
                ]
                await asyncio.gather(*tasks)
                await browser.close()
                if once:
                    break
                await asyncio.sleep(5)

    async def run_enrichment_worker(
        self,
        headless: bool,
        debug: bool,
        workers: int = 1,
        role: str = "full"
    ) -> None:
        if role == "processor":
            logger.info("Starting Enrichment PROCESSOR (No Browser)")
            # TODO: Implement enrichment processor loop if needed
            return

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

    async def _run_details_processor_loop(
        self,
        gm_list_item_queue: Any,
        enrichment_queue: Any,
        s3_client: Any,
        debug: bool,
        once: bool
    ) -> None:
        """
        PROCESSOR ROLE: Watches raw witness landing zone and transforms to Gold.
        Does NOT use a browser.
        """
        from ..core.paths import paths
        from ..models.campaigns.raw_witness import RawWitness
        from ..scrapers.google_maps_gmb_parser import parse_gmb_page
        from .processors.google_maps import GoogleMapsDetailsProcessor

        raw_dir = paths.campaign(self.campaign_name).path / "raw" / "gm-details"
        raw_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Processor Role active. Monitoring: {raw_dir}")

        while True:
            # 1. Discover Witnesses (Legacy .json files AND New directory structure)
            witness_files = list(raw_dir.rglob("*.json"))
            
            if not witness_files:
                if once:
                    return
                await asyncio.sleep(10)
                continue

            for file_path in witness_files:
                try:
                    logger.info(f"Processing Witness: {file_path.name}")
                    
                    # Determine if it's new directory format or legacy file format
                    if file_path.name == "metadata.json":
                        # New Format: raw/gm-details/{shard}/{place_id}/metadata.json
                        witness_dir = file_path.parent
                        html_path = witness_dir / "witness.html"
                        if not html_path.exists():
                            logger.warning(f"Metadata found but HTML missing for {witness_dir}")
                            continue
                            
                        with open(file_path, "r", encoding="utf-8") as f:
                            meta_data = json.load(f)
                        with open(html_path, "r", encoding="utf-8") as f:
                            html_content = f.read()
                            
                        # Reconstruct RawWitness for parser
                        witness = RawWitness(
                            place_id=meta_data["place_id"],
                            captured_at=datetime.fromisoformat(meta_data["captured_at"]),
                            processed_by=meta_data["processed_by"],
                            campaign_name=meta_data["campaign_name"],
                            url=meta_data["url"],
                            html=html_content,
                            metadata=meta_data.get("metadata", {}),
                            version=meta_data.get("version", "1.1.0")
                        )
                    else:
                        # Legacy Format: raw/gm-details/{shard}/{place_id}.json
                        with open(file_path, "r", encoding="utf-8") as f:
                            witness_data = json.load(f)
                            witness = RawWitness.model_validate(witness_data)

                    # 2. Parse HTML
                    details_dict = parse_gmb_page(witness.html, debug=debug)
                    
                    # 3. Transform to Gold
                    # We use the modular processor logic directly since we don't need a browser
                    # For now, we'll manually apply the logic
                    processor = GoogleMapsDetailsProcessor(processed_by=f"{self.processed_by}-processor")
                    
                    # Manually construct the prospect from healed data
                    from cocli.models.campaigns.indexes.google_maps_raw import GoogleMapsRawResult
                    from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
                    
                    raw_result = GoogleMapsRawResult(
                        Place_ID=witness.place_id,
                        Name=details_dict.get("Name") or witness.place_id,
                        Full_Address=details_dict.get("Full_Address", ""),
                        Website=details_dict.get("Website", ""),
                        Phone_1=details_dict.get("Phone", ""),
                        Domain=details_dict.get("Domain", ""),
                        Average_rating=details_dict.get("Average_rating"),
                        Reviews_count=details_dict.get("Reviews_count"),
                        GMB_URL=witness.url,
                        processed_by=processor.processed_by
                    )
                    
                    prospect = GoogleMapsProspect.from_raw(raw_result)
                    
                    # Save to WAL
                    csv_manager = ProspectsIndexManager(self.campaign_name)
                    if csv_manager.append_prospect(prospect):
                        logger.info(f"Success: Saved {witness.place_id} to WAL")
                        
                        # Save Enrichment file
                        prospect.save_enrichment()
                        
                        # Move witness to completed
                        if file_path.name == "metadata.json":
                            # New Format: Move the whole directory
                            witness_dir = file_path.parent
                            shard_name = witness_dir.parent.name
                            target_dir = raw_dir.parent / "completed" / shard_name / witness_dir.name
                            target_dir.parent.mkdir(parents=True, exist_ok=True)
                            
                            # Clean up target if exists (retry case)
                            if target_dir.exists():
                                import shutil
                                shutil.rmtree(target_dir)
                            
                            witness_dir.rename(target_dir)
                        else:
                            # Legacy Format: Move the single file
                            completed_dir = raw_dir.parent / "completed" / file_path.parent.name
                            completed_dir.mkdir(parents=True, exist_ok=True)
                            file_path.rename(completed_dir / file_path.name)
                        
                        logger.info(f"Success: Processed {witness.place_id}")

                except Exception as e:
                    logger.error(f"Error processing witness {file_path.name}: {e}", exc_info=True)
                    # Move to failed or leave for retry? Leave for now.
                    await asyncio.sleep(1)

            if once:
                break
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
        from ..models.companies.company import Company
        from ..models.campaigns.campaign import Campaign
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
                    logger.info("run_enrichment_worker(once=True): No tasks found in Enrichment queue.")
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
                    logger.info(f"Creating hollow company for enrichment task: {task.company_slug}")
                    company = Company(
                        name=task.company_slug, 
                        domain=task.domain, 
                        slug=task.company_slug
                    )
                
                # RECOVERY: Ensure domain is set even if company was found without it
                if not company.domain and task.domain:
                    company.domain = task.domain

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
                    # Load existing config first to get AWS context
                    config = load_campaign_config(self.campaign_name)
                    aws_config = config.get("aws", {})

                    # 0. Sync config from S3 (Efficient Targeted Sync)
                    from ..services.sync_service import SyncService
                    try:
                        # Use a dedicated SyncService instance for this iteration
                        # and run the sync in a thread to avoid blocking.
                        sync_service = SyncService(self.campaign_name, aws_config=aws_config)
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
                    
                    # Gossip Bridge DISABLED to prevent propagation of redundant field-level WAL junk
                    # if gossip_task is None or gossip_task.done():
                    #     # Start the Gossip Bridge in a thread to avoid blocking the event loop
                    #     from ..core.gossip_bridge import GossipBridge
                    #     def _run_gossip() -> None:
                    #         bridge = GossipBridge()
                    #         bridge.start()
                    #         try:
                    #             while True:
                    #                 time.sleep(1)
                    #         except Exception as e:
                    #             logger.error(f"Gossip Bridge thread error: {e}")
                    #         finally:
                    #             bridge.stop()
                    #     
                    #     logger.info("Starting Gossip Bridge via Supervisor...")
                    #     gossip_task = asyncio.create_task(asyncio.to_thread(_run_gossip))

                    config = load_campaign_config(self.campaign_name)
                    scaling = config.get("prospecting", {}).get("scaling", {}).get(self.processed_by, {})
                    target_scrape = scaling.get("gm-list", scaling.get("scrape", 0))
                    target_details = scaling.get("gm-details", scaling.get("details", 0))
                    target_enrich = scaling.get("enrichment", 0)

                    while len(scrape_tasks) < target_scrape:
                        new_id = len(scrape_tasks)
                        scrape_tasks[new_id] = asyncio.create_task(self._run_scrape_task_loop(browser, scrape_queue, gm_list_item_queue, s3_client, debug, False))
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
            s3_client.put_object(Bucket=self.bucket_name, Key=paths.s3.heartbeat(self.processed_by), Body=json.dumps(stats, indent=2), ContentType="application/json")
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
