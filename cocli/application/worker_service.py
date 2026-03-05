# POLICY: frictionless-data-policy-enforcement
import socket
import asyncio
import json
import logging
import os
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

from playwright.async_api import async_playwright, Browser, BrowserContext

from ..core.queue.factory import get_queue_manager
from ..scrapers.google_maps import scrape_google_maps
from ..models.campaigns.queues.gm_list import ScrapeTask
from ..models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem
from ..models.campaigns.queues.gm_details import GmItemTask
from ..models.campaigns.queues.base import QueueMessage
from ..core.config import load_campaign_config
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

    async def _launch_browser(self, playwright: Any, headless: bool) -> Browser:
        """Launches a browser, prioritizing msedge channel for stealth."""
        from typing import cast
        try:
            browser = await playwright.chromium.launch(
                headless=headless,
                channel="msedge",
                args=[
                    "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
                ]
            )
            return cast(Browser, browser)
        except Exception:
            browser = await playwright.chromium.launch(
                headless=headless,
                args=[
                    "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
                ]
            )
            return cast(Browser, browser)

    async def _run_scrape_task_loop(
        self,
        browser: Browser,
        scrape_queue: Any,
        gm_list_item_queue: Any,
        s3_client: Any,
        debug: bool,
        once: bool,
        headless: bool = True,
        workers: int = 1,
    ) -> None:
        while True:
            await asyncio.sleep(0.1)
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
                grid_tiles = [{"id": task.tile_id, "center_lat": task.latitude, "center_lon": task.longitude, "center": {"lat": task.latitude, "lon": task.longitude}}]
            
            try:
                location_param = {"latitude": str(task.latitude), "longitude": str(task.longitude)}
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
                        discovered_items.append(list_item)
                        gm_list_item_queue.push(list_item.to_task(task.campaign_name, force_refresh=False))

                if discovered_items:
                    try:
                        from .processors.gm_list import GmListProcessor
                        metadata = {"user_agent": USER_AGENT, "common_headers": ANTI_BOT_HEADERS, "timestamp": datetime.now(UTC).isoformat()}
                        processor = GmListProcessor(processed_by=self.processed_by, bucket_name=self.bucket_name)
                        await processor.process_results(task, discovered_items, s3_client=s3_client, metadata=metadata)
                    except Exception as res_err:
                        logger.warning(f"Failed to write batch result log: {res_err}")

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
        context: BrowserContext,
        gm_list_item_queue: Any,
        enrichment_queue: Any,
        s3_client: Any,
        debug: bool,
        once: bool,
    ) -> None:
        while True:
            if not context.browser or not context.browser.is_connected():
                break

            tasks: List[GmItemTask] = await asyncio.to_thread(gm_list_item_queue.poll, batch_size=1)
            if not tasks:
                if once:
                    return
                await asyncio.sleep(5)
                continue

            task = tasks[0]
            try:
                page = await context.new_page()
                try:
                    from .processors.google_maps import GoogleMapsDetailsProcessor
                    processor = GoogleMapsDetailsProcessor(processed_by=self.processed_by)
                    final_prospect_data = await processor.process(task, page, debug=debug)
                    
                    if final_prospect_data and final_prospect_data.domain:
                        enrichment_queue.push(QueueMessage(domain=str(final_prospect_data.domain), company_slug=slugify(final_prospect_data.name), campaign_name=task.campaign_name, force_refresh=task.force_refresh, ack_token=None))
                    
                    gm_list_item_queue.ack(task)
                finally:
                    await page.close()
                if once:
                    return
            except Exception as e:
                logger.error(f"Detail Task Failed: {e}")
                gm_list_item_queue.nack(task)
                if once:
                    return
                break

    async def _run_enrichment_task_loop(
        self,
        context: BrowserContext,
        enrichment_queue: Any,
        debug: bool,
        once: bool,
        s3_client: Optional[Any] = None,
    ) -> None:
        from ..core.enrichment import enrich_company_website
        from ..models.companies.company import Company
        from ..models.campaigns.campaign import Campaign

        try:
            campaign_obj = Campaign.load(self.campaign_name)
        except Exception:
            return

        while True:
            tasks: List[QueueMessage] = await asyncio.to_thread(enrichment_queue.poll, batch_size=1)
            if not tasks:
                if once:
                    return
                await asyncio.sleep(5)
                continue

            task = tasks[0]
            try:
                company = Company.get(task.company_slug) or Company(name=task.company_slug, domain=task.domain, slug=task.company_slug)
                website_data = await enrich_company_website(browser=context, company=company, campaign=campaign_obj, force=task.force_refresh, debug=debug)
                if website_data:
                    website_data.save(task.company_slug)
                enrichment_queue.ack(task)
                if once:
                    return
            except Exception as e:
                logger.error(f"Enrichment Task Failed: {e}")
                enrichment_queue.nack(task)
                if once:
                    return
                break

    async def _run_command_poller_loop(self, command_queue: Any, s3_client: Any) -> None:
        from ..application.campaign_service import CampaignService
        import shlex
        while True:
            try:
                campaign_service = CampaignService(self.campaign_name)
                commands = await asyncio.to_thread(command_queue.poll, batch_size=1)
                for cmd in commands:
                    parts = shlex.split(cmd.command)
                    if "add-exclude" in cmd.command:
                        await asyncio.to_thread(campaign_service.add_exclude, parts[parts.index("add-exclude")+1])
                    await asyncio.to_thread(command_queue.ack, cmd)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(10)
            await asyncio.sleep(5)

    async def run_worker(self, headless: bool, debug: bool, once: bool = False, workers: int = 1, role: str = "full") -> None:
        self.role = role
        async with async_playwright() as p:
            browser = await self._launch_browser(p, headless)
            s3_client = self.get_s3_client()
            scrape_q = get_queue_manager("scrape", use_cloud=True, queue_type="scrape", campaign_name=self.campaign_name, s3_client=s3_client)
            details_q = get_queue_manager("details", use_cloud=True, queue_type="gm_list_item", campaign_name=self.campaign_name, s3_client=s3_client)
            tasks = [self._run_scrape_task_loop(browser, scrape_q, details_q, s3_client, debug, once, headless, workers) for _ in range(workers)]
            await asyncio.gather(*tasks)
            await browser.close()

    async def run_details_worker(self, headless: bool, debug: bool, once: bool = False, workers: int = 1, role: str = "full") -> None:
        self.role = role
        async with async_playwright() as p:
            browser = await self._launch_browser(p, headless)
            context = await browser.new_context(user_agent=USER_AGENT, extra_http_headers=ANTI_BOT_HEADERS)
            await setup_optimized_context(context)
            s3_client = self.get_s3_client()
            details_q = get_queue_manager("details", use_cloud=True, queue_type="gm_list_item", campaign_name=self.campaign_name, s3_client=s3_client)
            enrich_q = get_queue_manager("enrichment", use_cloud=True, queue_type="enrichment", campaign_name=self.campaign_name, s3_client=s3_client)
            tasks = [self._run_details_task_loop(context, details_q, enrich_q, s3_client, debug, once) for _ in range(workers)]
            await asyncio.gather(*tasks)
            await browser.close()

    async def run_enrichment_worker(self, headless: bool, debug: bool, once: bool = False, workers: int = 1) -> None:
        async with async_playwright() as p:
            browser = await self._launch_browser(p, headless)
            context = await browser.new_context(user_agent=USER_AGENT, extra_http_headers=ANTI_BOT_HEADERS)
            await setup_optimized_context(context)
            s3_client = self.get_s3_client()
            enrich_q = get_queue_manager("enrichment", use_cloud=True, queue_type="enrichment", campaign_name=self.campaign_name, s3_client=s3_client)
            tasks = [self._run_enrichment_task_loop(context, enrich_q, debug, once, s3_client) for _ in range(workers)]
            await asyncio.gather(*tasks)
            await browser.close()

    async def _push_supervisor_heartbeat(self, s3_client: Any, s: Dict[int, asyncio.Task[Any]], d: Dict[int, asyncio.Task[Any]], e: Dict[int, asyncio.Task[Any]]) -> None:
        import psutil
        from ..core.paths import paths
        stats = {
            "timestamp": datetime.now(UTC).isoformat(), 
            "hostname": self.processed_by, 
            "system": {"cpu": psutil.cpu_percent(), "mem": psutil.virtual_memory().percent}, 
            "workers": {"s": len(s), "d": len(d), "e": len(e)}
        }
        s3_client.put_object(Bucket=self.bucket_name, Key=paths.s3.heartbeat(self.processed_by), Body=json.dumps(stats), ContentType="application/json")

    async def run_supervisor(self, headless: bool, debug: bool, interval: int) -> None:
        async with async_playwright() as p:
            browser = await self._launch_browser(p, headless)
            s_tasks: Dict[int, asyncio.Task[Any]] = {}
            d_tasks: Dict[int, asyncio.Task[Any]] = {}
            e_tasks: Dict[int, asyncio.Task[Any]] = {}
            s3_client = self.get_s3_client()
            while True:
                try:
                    await self._push_supervisor_heartbeat(s3_client, s_tasks, d_tasks, e_tasks)
                except Exception as ex:
                    logger.error(f"Supervisor error: {ex}")
                await asyncio.sleep(interval)
            await browser.close()

    async def run_orchestrated_workers(self, worker_definitions: List[Any], headless: bool = True, debug: bool = False) -> None:
        """
        Launches and manages multiple named worker instances.
        """
        from cocli.core.gossip_bridge import bridge
        if bridge:
            try:
                bridge.start()
            except Exception:
                pass

        worker_tasks = []
        for wd in worker_definitions:
            worker_service = WorkerService(campaign_name=self.campaign_name, role=wd.role, processed_by=f"{self.processed_by}-{wd.name}")
            if wd.content_type == "gm-list":
                coro = worker_service.run_worker(headless=headless, debug=debug, once=False, workers=wd.workers)
            elif wd.content_type == "gm-details":
                coro = worker_service.run_details_worker(headless=headless, debug=debug, once=False, workers=wd.workers, role=wd.role)
            elif wd.content_type == "enrichment":
                coro = worker_service.run_enrichment_worker(headless=headless, debug=debug, once=False, workers=wd.workers)
            else:
                continue
            worker_tasks.append(asyncio.create_task(coro))

        if worker_tasks:
            await asyncio.gather(*worker_tasks)

    async def get_cluster_health(self) -> List[Dict[str, Any]]:
        """
        Checks health of all Raspberry Pi workers.
        """
        import subprocess
        scaling = self.config.get("prospecting", {}).get("scaling", {})
        nodes = []
        for host_key in scaling.keys():
            if host_key != "fargate":
                host = host_key if "." in host_key else f"{host_key}.pi"
                nodes.append({"host": host, "label": host_key.capitalize()})
        
        results = []
        for node in nodes:
            host = str(node.get("host"))
            try:
                cmd = "uptime; vcgencmd measure_volts; vcgencmd get_throttled; docker ps --format '{{.Names}}|{{.Status}}'"
                res = await asyncio.to_thread(subprocess.run, ["ssh", "-o", "ConnectTimeout=3", f"mstouffer@{host}", cmd], capture_output=True, text=True)
                host_info = {"host": host, "online": res.returncode == 0}
                results.append(host_info)
            except Exception:
                results.append({"host": host, "online": False})
        return results
