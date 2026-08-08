# POLICY: frictionless-data-policy-enforcement
import socket
import asyncio
import json
import logging
import os
import time
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional, Set

from playwright.async_api import async_playwright, Browser, BrowserContext

from ..core.queue.factory import get_queue_manager
from ..scrapers.google.google_maps import scrape_google_maps
from ..models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem
from ..models.campaigns.queues.gm_details import GmItemTask
from ..models.campaigns.queues.base import QueueMessage
from ..core.config import load_campaign_config
from ..core.paths import paths
from ..utils.playwright_utils import setup_optimized_context
from ..utils.headers import ANTI_BOT_HEADERS, USER_AGENT
from ..utils.async_iteration import iterate_with_idle_timeout
from ..core.text_utils import slugify

logger = logging.getLogger(__name__)

# Max time to wait for the *next* new gm-list result before treating a
# scrape task as stuck (resets on every item found - see
# iterate_with_idle_timeout). 90s comfortably covers a slow scroll/hydration
# cycle without waiting anywhere near as long as the old fixed 900s ceiling.
SCRAPE_IDLE_TIMEOUT_S = 90
# Hard backstop regardless of progress, for a source that never stalls but
# also never finishes (e.g. a duplicate-heavy feed with no clean end).
SCRAPE_ABSOLUTE_TIMEOUT_S = 1500


def _is_orphaned_playwright_future(context: Dict[str, Any]) -> bool:
    """True for the general "Future/Task exception was never retrieved"
    shape from an orphaned Playwright internal Future, documented on ticket
    investigate-orphaned-playwright-future-targetclosederror-from-idle-timeout-cancellation.

    Root cause: any Playwright async operation that gets cancelled mid-flight
    (iterate_with_idle_timeout cancels the *task* running the scrape loop
    whenever it's stuck waiting for a low-level Playwright call) can strand
    that operation's own internal Future/Task - Playwright has no hook for
    "my caller just got cancelled, let me clean up." Confirmed two concrete
    shapes so far, both from reading Playwright's own source, not guessed:
    - Channel._inner_send() (_impl/_connection.py) awaits
      asyncio.wait({..., callback.future}) and only cancels callback.future
      in the line right after that await returns; asyncio.wait's own
      cancellation semantics skip that line when the *awaiter* (not the
      future itself) is cancelled, leaving callback.future registered in
      Connection._callbacks forever.
    - Locator polling (e.g. `locator(...).first` visibility waits) can raise
      its own TimeoutError into a similarly abandoned Future when the
      surrounding task is cancelled before that poll resolves.
    Both are bugs in Playwright's own internals (missing cancellation
    cleanup), not something patchable from our call site - we have no
    reference to the leaked Future from outside Playwright's internals.
    Matching on "exception's type lives in a playwright module" rather than
    a specific class name is deliberate: this covers whatever shape
    Playwright's internals produce next, without also swallowing our own
    IdleTimeoutError (module cocli.utils.async_iteration - already caught
    and logged deliberately elsewhere, must keep flowing normally) or any
    unrelated orphaned-Future warning from our own code.
    """
    exc = context.get("exception")
    message = context.get("message", "")
    return (
        exc is not None
        and type(exc).__module__.startswith("playwright")
        and "never retrieved" in message
    )


def _write_orphaned_playwright_future_record(
    campaign_name: str, context: Dict[str, Any]
) -> None:
    """Append a structured record of a suppressed orphaned-Playwright-Future
    warning to a durable, campaign-scoped file - downgrading the console
    warning to debug must not also mean losing track of how often this
    actually happens.

    Written under paths.campaign(campaign_name).path, which is bind-mounted
    to the host (~/repos/data - see ClusterService._restart_node) and
    survives container restarts, unlike stdout/stderr (only captured by
    `docker logs`, subject to the log rotation policy). Note this currently
    requires SSHing to the node to read - ClusterService.pull_scraped_tiles/
    sync_and_audit only pull queues/ and raw/, not logs/.
    """
    try:
        log_path = (
            paths.campaign(campaign_name).path / "logs" / "playwright_leaked_futures.jsonl"
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        exc = context.get("exception")
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "exception_type": type(exc).__name__,
            "exception_module": type(exc).__module__,
            "exception_str": str(exc),
            "message": context.get("message", ""),
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        logger.debug(
            "Failed to write orphaned-Playwright-Future tracking record", exc_info=True
        )


def install_playwright_leak_exception_handler(
    loop: asyncio.AbstractEventLoop, campaign_name: str
) -> None:
    """Downgrade the known orphaned-Playwright-Future noise (see
    _is_orphaned_playwright_future) to a debug log plus a durable tracking
    record (_write_orphaned_playwright_future_record) instead of asyncio's
    default unhandled-exception warning; everything else still goes through
    the loop's normal default handler unchanged."""

    def _handler(loop: asyncio.AbstractEventLoop, context: Dict[str, Any]) -> None:
        if _is_orphaned_playwright_future(context):
            logger.debug(
                "Suppressed known orphaned-Playwright-Future noise "
                "(ticket: investigate-orphaned-playwright-future-targetclosederror-"
                "from-idle-timeout-cancellation): %s",
                context.get("exception"),
            )
            _write_orphaned_playwright_future_record(campaign_name, context)
            return
        loop.default_exception_handler(context)

    loop.set_exception_handler(_handler)


def route_discovered_list_item(
    list_item: GoogleMapsListItem,
    *,
    campaign_name: str,
    enrichment_queue: Any,
    gm_list_item_queue: Any,
    processed_by: str,
) -> None:
    """Per-discovery routing decision for the gm-list scraper.

    domain present -> bypass gm-details entirely, push straight to
    enrichment AND persist a durable WAL record. The details stage would
    normally write this record via add_to_wal() (see
    GoogleMapsDetailsProcessor.process()) - bypassing details here must not
    also bypass that record, or this discovery never reaches the prospects
    checkpoint except via a manual compact_gm_list_results() run.

    No domain -> queue for gm-details, which persists its own WAL record
    once it finds one.

    Extracted as a plain, synchronous function (rather than inline in the
    async scrape loop) so it's testable without mocking a Playwright
    browser - see task-agent ticket
    gm-list-output-router-decouple-fan-out-from-scraper-workers for the
    larger router/connector split this is a small step towards.
    """
    from ..core.prospects_csv_manager import ProspectsIndexManager
    from ..core.transformers.gm_list_item_to_prospect import (
        transform_gm_list_item_to_google_maps_prospect,
    )

    if list_item.domain:
        logger.info(
            f"Bypassing details: domain '{list_item.domain}' found for "
            f"'{list_item.name}'. Routing directly to enrichment."
        )
        enrichment_queue.push(
            QueueMessage(
                domain=str(list_item.domain),
                company_slug=slugify(str(list_item.name) if list_item.name else ""),
                campaign_name=campaign_name,
                force_refresh=False,
                ack_token=None,
            )
        )
        prospect = transform_gm_list_item_to_google_maps_prospect(list_item)
        prospect.processed_by = processed_by
        ProspectsIndexManager(campaign_name).add_to_wal(prospect)
    else:
        gm_list_item_queue.push(list_item.to_task(campaign_name, force_refresh=False))


class WorkerService:
    def __init__(self, campaign_name: str, processed_by: Optional[str] = None, role: str = "full"):
        self.campaign_name = campaign_name
        self.processed_by = processed_by or (os.getenv("COCLI_HOSTNAME") or socket.gethostname().split(".")[0])
        self.role = role
        self._load_config()
        self.worker_tasks: List[asyncio.Task[Any]] = []
        self.child_workers: List["WorkerService"] = []
        self.content_type: Optional[str] = None
        self.worker_count: int = 1
        self.last_activity_ts: Optional[float] = None
        self._running = False

    def _load_config(self) -> None:
        self.config = load_campaign_config(self.campaign_name)
        self.aws_config = self.config.get("aws", {})
        self.bucket_name = (
            self.aws_config.get("data_bucket_name") 
            or self.aws_config.get("cocli_data_bucket_name") 
            or f"cocli-data-{self.campaign_name}"
        )

    async def _watch_remote_config(self) -> None:
        """Watches for config updates received via gossip."""
        from ..core.paths import paths
        update_dir = paths.root / "remote_updates"
        update_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"WorkerService: Watching for config updates in {update_dir}")
        
        last_processed = 0
        while self._running:
            try:
                # Find the latest config file
                updates = sorted(update_dir.glob("config_*.json"))
                if updates:
                    latest = updates[-1]
                    # Format: config_TIMESTAMP.json
                    try:
                        ts = int(latest.stem.split("_")[1])
                        if ts > last_processed:
                            logger.info(f"Applying hot config update from gossip: {latest.name}")
                            with open(latest, "r") as f:
                                new_scaling = json.load(f)
                            
                            # Update local campaign config.toml for persistence
                            from ..core.paths import paths
                            config_path = paths.campaign(self.campaign_name).path / "config.toml"
                            if config_path.exists():
                                import toml
                                with open(config_path, "r") as f:
                                    full_config = toml.load(f)
                                
                                # Merge scaling update
                                if "prospecting" not in full_config:
                                    full_config["prospecting"] = {}
                                full_config["prospecting"]["scaling"] = new_scaling
                                
                                with open(config_path, "w") as f:
                                    toml.dump(full_config, f)
                                
                                logger.info("Local config.toml updated with gossip scaling.")
                                self._load_config()
                                await self._rebalance_workers()
                            
                            last_processed = ts
                    except (IndexError, ValueError):
                        pass
            except Exception as e:
                logger.error(f"Error in config watcher: {e}")
            
            await asyncio.sleep(5)

    async def _heartbeat_loop(self, interval: int = 30) -> None:
        """Periodic heartbeat broadcast."""
        logger.info(f"WorkerService: Starting heartbeat loop ({interval}s)")
        s3_client = self.get_s3_client()
        while self._running:
            try:
                await self._push_supervisor_heartbeat(s3_client)
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")
            await asyncio.sleep(interval)

    async def _rebalance_workers(self) -> None:
        """Restarts workers based on updated scaling config."""
        logger.info("Rebalancing workers due to config update...")
        # Cancel current tasks
        for task in self.worker_tasks:
            if not task.done():
                task.cancel()

        if self.worker_tasks:
            await asyncio.gather(*self.worker_tasks, return_exceptions=True)
            self.worker_tasks = []

        # The workers cancelled above are about to be replaced wholesale -
        # drop their child_workers entries too. Production incident
        # (2026-07-07): this list used to only ever get populated at
        # startup by run_orchestrated_workers(); _rebalance_workers()
        # replaced the actual running workers without touching it, so the
        # heartbeat/audit kept reporting a frozen, aging last_activity_ts
        # for content types a rebalance had already replaced (false STALE
        # verdicts) and never showed content types a rebalance added fresh
        # (invisible designation) - see incident ticket for full evidence.
        self.child_workers = []

        # Resolve Host-Specific Worker Definitions
        from ..models.campaigns.worker_config import WorkerDefinition
        hostname = self.processed_by.split("-")[0] # Strip previous worker suffixes if present

        scaling = self.config.get("prospecting", {}).get("scaling", {})
        node_scaling = {}
        for h, s in scaling.items():
            if h.startswith(hostname):
                node_scaling = s
                break

        if not node_scaling:
            logger.warning(f"No scaling config found for host: {hostname}")
            return

        # Resolve default IoT profile from campaign config
        default_iot_profile = self.aws_config.get("iot_profiles", ["roadmap-iot"])[0]

        worker_defs = []
        for c_type, count in node_scaling.items():
            if count > 0:
                worker_defs.append(WorkerDefinition(
                    name=f"{hostname}-{c_type}",
                    role="full",
                    content_type=c_type,
                    workers=count,
                    iot_profile=default_iot_profile
                ))

        # Google Maps conclusively blocks Fargate/data-center IP ranges (see
        # CLAUDE.md "Known Issues") - the same hard rule
        # run_orchestrated_workers() enforces at startup; a hot-reload must
        # not be able to bypass it.
        running_in_fargate = bool(os.getenv("COCLI_RUNNING_IN_FARGATE"))

        # Restart: mirror run_orchestrated_workers()'s pattern of a
        # dedicated child WorkerService per content type, registered in
        # child_workers, so the heartbeat's designation/last-activity
        # aggregation sees these workers the same way it sees the ones
        # created at startup.
        for wd in worker_defs:
            if running_in_fargate and wd.content_type in ("gm-list", "gm-details"):
                logger.error(
                    f"  ✗ Refusing to launch '{wd.content_type}' worker '{wd.name}' on Fargate "
                    "- Google Maps blocks Fargate IPs (see CLAUDE.md). Check config.toml."
                )
                continue

            worker_service = WorkerService(campaign_name=self.campaign_name, role=wd.role, processed_by=f"{self.processed_by}-{wd.name}")
            worker_service.content_type = wd.content_type
            worker_service.worker_count = wd.workers
            self.child_workers.append(worker_service)

            if wd.content_type == "gm-list":
                coro = worker_service.run_worker(headless=True, debug=False, once=False, workers=wd.workers)
            elif wd.content_type == "gm-details":
                coro = worker_service.run_details_worker(headless=True, debug=False, once=False, workers=wd.workers, role=wd.role)
            elif wd.content_type == "enrichment":
                coro = worker_service.run_enrichment_worker(headless=True, debug=False, once=False, workers=wd.workers)
            else:
                continue
            self.worker_tasks.append(asyncio.create_task(coro))

        logger.info(f"Rebalance complete. Now running {len(self.worker_tasks)} worker tasks.")

    def get_s3_client(self) -> Any:
        from ..core.reporting import get_boto3_session
        profile = f"{self.campaign_name}-iot"
        try:
            session = get_boto3_session(self.config, profile_name=profile)
            session.get_credentials()
            return session.client("s3")
        except Exception as e:
            logger.warning(
                f"Failed to initialize S3 client with profile {profile}: {e}. "
                "Falling back to default/configured session."
            )
            session = get_boto3_session(self.config)
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
        gm_list_item_queue: Any,
        s3_client: Any,
        debug: bool,
        once: bool,
        headless: bool = True,
        workers: int = 1,
    ) -> None:
        from ..core.queue.factory import get_queue_manager

        while True:
            self.last_activity_ts = time.time()
            await asyncio.sleep(0.1)
            try:
                if not browser.is_connected():
                    logger.error("Browser is disconnected. Breaking task loop to restart.")
                    break
            except Exception as e:
                logger.error(f"Browser check failed: {e}")
                break

            # Poll from gm-list queue with lease-based coordination
            gm_list_queue = get_queue_manager("gm-list", use_cloud=True, queue_type="gm-list", campaign_name=self.campaign_name, s3_client=s3_client)
            enrichment_queue = get_queue_manager("enrichment", use_cloud=True, queue_type="enrichment", campaign_name=self.campaign_name, s3_client=s3_client)

            # Poll for next scrape task (includes automatic lease creation)
            tasks = gm_list_queue.poll(batch_size=1)

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
                # Keep track of Place IDs in this specific search to avoid redundant enqueuing
                pushed_place_ids: Set[str] = set()

                # Idle timeout (resets per item) instead of one fixed ceiling
                # for the whole tile+phrase task - a source that keeps
                # yielding real results can run indefinitely; a source that
                # stops producing (observed live: the sidebar scanner's own
                # stall-check only watches raw DOM element count, which can
                # keep climbing - ads, re-renders - even when every place_id
                # found is already a duplicate, so it never yields anything
                # new and never trips its own break condition) now fails in
                # SCRAPE_IDLE_TIMEOUT_S instead of burning the full ceiling.
                async for list_item in iterate_with_idle_timeout(
                    scrape_google_maps(
                        browser=browser,
                        location_param=location_param,
                        search_strings=[task.search_phrase],
                        campaign_name=task.campaign_name,
                        grid_tiles=grid_tiles,
                        debug=debug,
                        s3_client=s3_client,
                        s3_bucket=self.bucket_name,
                        processed_by=self.processed_by,
                    ),
                    idle_timeout_s=SCRAPE_IDLE_TIMEOUT_S,
                    absolute_timeout_s=SCRAPE_ABSOLUTE_TIMEOUT_S,
                ):
                    if not list_item.place_id:
                        continue

                    discovered_items.append(list_item)

                    if list_item.place_id not in pushed_place_ids:
                        route_discovered_list_item(
                            list_item,
                            campaign_name=task.campaign_name,
                            enrichment_queue=enrichment_queue,
                            gm_list_item_queue=gm_list_item_queue,
                            processed_by=self.processed_by,
                        )
                        pushed_place_ids.add(list_item.place_id)

                if discovered_items:
                    try:
                        from .processors.gm_list import GmListProcessor
                        metadata = {"user_agent": USER_AGENT, "common_headers": ANTI_BOT_HEADERS, "timestamp": datetime.now(UTC).isoformat()}
                        processor = GmListProcessor(processed_by=self.processed_by, bucket_name=self.bucket_name)
                        await processor.process_results(task, discovered_items, s3_client=s3_client, metadata=metadata)
                    except Exception as res_err:
                        logger.warning(f"Failed to write batch result log: {res_err}")

                logger.info(f"Completed scrape task: {task.tile_id} × {task.search_phrase}")

                task.result_count = len(discovered_items)
                # Acknowledge successful task completion (removes lease)
                gm_list_queue.ack(task)

                if once:
                    return
            except Exception as e:
                logger.error(f"Task Failed: {e}")
                # Negative acknowledge on failure (removes lease, task stays available)
                gm_list_queue.nack(task)

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
            self.last_activity_ts = time.time()
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
                        enrichment_queue.push(QueueMessage(domain=str(final_prospect_data.domain), company_slug=slugify(str(final_prospect_data.name) if final_prospect_data.name else ""), campaign_name=task.campaign_name, force_refresh=task.force_refresh, ack_token=None))
                    
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
                await asyncio.sleep(5)

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
        from ..models.company_name import CompanyName
        from ..models.campaigns.campaign import Campaign

        try:
            campaign_obj = Campaign.load(self.campaign_name)
        except Exception:
            return

        while True:
            self.last_activity_ts = time.time()
            if not context.browser or not context.browser.is_connected():
                logger.error("Browser is disconnected. Breaking task loop to restart.")
                break

            tasks: List[QueueMessage] = await asyncio.to_thread(enrichment_queue.poll, batch_size=1)
            if not tasks:
                if once:
                    return
                await asyncio.sleep(5)
                continue

            task = tasks[0]
            try:
                company = Company.get(task.company_slug) or Company(name=CompanyName(task.company_slug), domain=task.domain, slug=task.company_slug)
                website_data = await enrich_company_website(
                    browser=context,
                    company=company,
                    campaign=campaign_obj,
                    force=task.force_refresh,
                    debug=debug,
                    processed_by=self.processed_by
                )
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
                await asyncio.sleep(5)

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
        max_session_duration_s = 4 * 3600  # Recycle Playwright browser every 4 hours to prevent RAM leaks
        while self._running or not once:
            session_start = time.time()
            try:
                async with async_playwright() as p:
                    browser = await self._launch_browser(p, headless)
                    s3_client = self.get_s3_client()
                    details_q = get_queue_manager("details", use_cloud=True, queue_type="gm_list_item", campaign_name=self.campaign_name, s3_client=s3_client)
                    coros = [self._run_scrape_task_loop(browser, details_q, s3_client, debug, once, headless, workers) for _ in range(workers)]
                    tasks: List[asyncio.Task[Any]] = [asyncio.create_task(c) for c in coros]
                    
                    # Run until workers finish or max session duration reached
                    while time.time() - session_start < max_session_duration_s:
                        done, pending = await asyncio.wait(tasks, timeout=30, return_when=asyncio.FIRST_EXCEPTION)
                        if once:
                            break
                        # Check if any task crashed
                        for t in done:
                            if t.exception():
                                logger.error(f"Scrape worker task crashed: {t.exception()}")
                        if any(t.done() for t in tasks):
                            break

                    for t in tasks:
                        if not t.done():
                            t.cancel()
                    await browser.close()
            except Exception as e:
                logger.error(f"Browser session crash in run_worker: {e}")

            if once:
                break
            logger.info("Recycling Playwright browser session for fresh memory footprint...")
            await asyncio.sleep(5)

    async def run_details_worker(self, headless: bool, debug: bool, once: bool = False, workers: int = 1, role: str = "full") -> None:
        self.role = role
        max_session_duration_s = 4 * 3600
        while self._running or not once:
            session_start = time.time()
            try:
                async with async_playwright() as p:
                    browser = await self._launch_browser(p, headless)
                    context = await browser.new_context(user_agent=USER_AGENT, extra_http_headers=ANTI_BOT_HEADERS)
                    await setup_optimized_context(context)
                    s3_client = self.get_s3_client()
                    details_q = get_queue_manager("details", use_cloud=True, queue_type="gm_list_item", campaign_name=self.campaign_name, s3_client=s3_client)
                    enrich_q = get_queue_manager("enrichment", use_cloud=True, queue_type="enrichment", campaign_name=self.campaign_name, s3_client=s3_client)
                    coros = [self._run_details_task_loop(context, details_q, enrich_q, s3_client, debug, once) for _ in range(workers)]
                    tasks: List[asyncio.Task[Any]] = [asyncio.create_task(c) for c in coros]
                    
                    while time.time() - session_start < max_session_duration_s:
                        done, pending = await asyncio.wait(tasks, timeout=30, return_when=asyncio.FIRST_EXCEPTION)
                        if once:
                            break
                        if any(t.done() for t in tasks):
                            break

                    for t in tasks:
                        if not t.done():
                            t.cancel()
                    await browser.close()
            except Exception as e:
                logger.error(f"Browser session crash in run_details_worker: {e}")

            if once:
                break
            logger.info("Recycling Playwright details browser session for fresh memory footprint...")
            await asyncio.sleep(5)

    async def run_enrichment_worker(self, headless: bool, debug: bool, once: bool = False, workers: int = 1) -> None:
        max_session_duration_s = 4 * 3600
        while self._running or not once:
            session_start = time.time()
            try:
                async with async_playwright() as p:
                    browser = await self._launch_browser(p, headless)
                    context = await browser.new_context(user_agent=USER_AGENT, extra_http_headers=ANTI_BOT_HEADERS)
                    from ..utils.playwright_utils import setup_stealth_context
                    await setup_stealth_context(context)
                    s3_client = self.get_s3_client()
                    enrich_q = get_queue_manager("enrichment", use_cloud=True, queue_type="enrichment", campaign_name=self.campaign_name, s3_client=s3_client)
                    coros = [self._run_enrichment_task_loop(context, enrich_q, debug, once, s3_client) for _ in range(workers)]
                    tasks: List[asyncio.Task[Any]] = [asyncio.create_task(c) for c in coros]
                    
                    while time.time() - session_start < max_session_duration_s:
                        done, pending = await asyncio.wait(tasks, timeout=30, return_when=asyncio.FIRST_EXCEPTION)
                        if once:
                            break
                        if any(t.done() for t in tasks):
                            break

                    for t in tasks:
                        if not t.done():
                            t.cancel()
                    await browser.close()
            except Exception as e:
                logger.error(f"Browser session crash in run_enrichment_worker: {e}")

            if once:
                break
            logger.info("Recycling Playwright enrichment browser session for fresh memory footprint...")
            await asyncio.sleep(5)



    async def _push_supervisor_heartbeat(self, s3_client: Any) -> None:
        import psutil
        from ..core.paths import paths
        from ..models.wal.record import HeartbeatDatagram
        from ..core.gossip_bridge import bridge
        from ..core.logging_config import get_recent_error_count, get_recent_error_messages

        cpu_usage = psutil.cpu_percent()
        mem_usage = psutil.virtual_memory().percent

        # Real per-content-type designation/activity from the child workers this
        # orchestrator actually launched (run_orchestrated_workers populates
        # self.child_workers) - previously this was always {} regardless of what
        # was running, which is why the heartbeat's worker counts were always 0.
        designation: Dict[str, int] = {}
        last_activity: Dict[str, str] = {}
        for child in self.child_workers:
            if not child.content_type:
                continue
            designation[child.content_type] = designation.get(child.content_type, 0) + child.worker_count
            if child.last_activity_ts is not None:
                ts_iso = datetime.fromtimestamp(child.last_activity_ts, UTC).isoformat()
                if child.content_type not in last_activity or ts_iso > last_activity[child.content_type]:
                    last_activity[child.content_type] = ts_iso

        worker_count = sum(designation.values())

        stats = {
            "timestamp": datetime.now(UTC).isoformat(),
            "hostname": self.processed_by,
            "campaign": self.campaign_name,
            "system": {"cpu": cpu_usage, "mem": mem_usage},
            "workers": {
                "s": designation.get("gm-list", 0),
                "d": designation.get("gm-details", 0),
                "e": designation.get("enrichment", 0),
            },
            "designation": designation,
            "last_activity": last_activity,
            "error_count_30m": get_recent_error_count(1800),
            "recent_errors": get_recent_error_messages(),
        }

        # Write local copy for container/health checks
        try:
            with open("/tmp/cocli_heartbeat.json", "w") as f:
                json.dump(stats, f)
        except Exception as local_err:
            logger.debug(f"Failed to write local heartbeat: {local_err}")

        # 1. Durability Tier (S3)
        try:
            s3_client.put_object(Bucket=self.bucket_name, Key=paths.s3.heartbeat(self.processed_by), Body=json.dumps(stats), ContentType="application/json")
        except Exception as s3_err:
            logger.debug(f"S3 Heartbeat failed: {s3_err}")

        # 2. Real-Time Tier (Gossip)
        if bridge and bridge.running:
            try:
                from ..core.environment import get_environment
                hb = HeartbeatDatagram(
                    campaign_name=self.campaign_name,
                    node_id=self.processed_by,
                    timestamp=str(stats["timestamp"]),
                    load_avg=cpu_usage, # We use CPU % as a proxy for load in the datagram
                    memory_percent=mem_usage,
                    worker_count=worker_count,
                    active_tasks=worker_count, # For now, assume all workers are active if in the loop
                    environment=get_environment().value
                )
                bridge.broadcast_msg(hb.to_usv())
            except Exception as gossip_err:
                logger.debug(f"Gossip Heartbeat failed: {gossip_err}")

    async def run_supervisor(self, headless: bool, debug: bool, interval: int) -> None:
        async with async_playwright() as p:
            browser = await self._launch_browser(p, headless)
            s3_client = self.get_s3_client()
            while True:
                try:
                    await self._push_supervisor_heartbeat(s3_client)
                except Exception as ex:
                    logger.error(f"Supervisor error: {ex}")
                await asyncio.sleep(interval)
            await browser.close()

    async def run_orchestrated_workers(self, worker_definitions: List[Any], headless: bool = True, debug: bool = False) -> None:
        """
        Launches and manages multiple named worker instances.
        """
        install_playwright_leak_exception_handler(asyncio.get_running_loop(), self.campaign_name)
        self._running = True
        from cocli.core.gossip_bridge import bridge
        if bridge:
            try:
                bridge.start()
            except Exception:
                pass

        # Start Config Watcher
        asyncio.create_task(self._watch_remote_config())

        # Start Heartbeat Loop
        asyncio.create_task(self._heartbeat_loop())

        logger.info(f"Orchestrating {len(worker_definitions)} worker definition(s)")

        # Google Maps conclusively blocks Fargate/data-center IP ranges (see
        # CLAUDE.md "Known Issues"). This is a hard rule, not just a missing-
        # config fallback: regardless of what config.toml says, gm-list/
        # gm-details must never be launched on Fargate.
        running_in_fargate = bool(os.getenv("COCLI_RUNNING_IN_FARGATE"))

        self.worker_tasks = []
        for wd in worker_definitions:
            if running_in_fargate and wd.content_type in ("gm-list", "gm-details"):
                logger.error(
                    f"  ✗ Refusing to launch '{wd.content_type}' worker '{wd.name}' on Fargate "
                    "- Google Maps blocks Fargate IPs (see CLAUDE.md). Check config.toml."
                )
                continue
            logger.info(f"Starting worker: {wd.name} (type={wd.content_type}, workers={wd.workers})")
            worker_service = WorkerService(campaign_name=self.campaign_name, role=wd.role, processed_by=f"{self.processed_by}-{wd.name}")
            worker_service.content_type = wd.content_type
            worker_service.worker_count = wd.workers
            self.child_workers.append(worker_service)
            if wd.content_type == "gm-list":
                logger.info("  → Launching run_worker for gm-list")
                coro = worker_service.run_worker(headless=headless, debug=debug, once=False, workers=wd.workers)
            elif wd.content_type == "gm-details":
                logger.info("  → Launching run_details_worker")
                coro = worker_service.run_details_worker(headless=headless, debug=debug, once=False, workers=wd.workers, role=wd.role)
            elif wd.content_type == "enrichment":
                logger.info("  → Launching run_enrichment_worker")
                coro = worker_service.run_enrichment_worker(headless=headless, debug=debug, once=False, workers=wd.workers)
            else:
                logger.warning(f"  ✗ Unknown content_type: {wd.content_type}, skipping")
                continue
            self.worker_tasks.append(asyncio.create_task(coro))

        logger.info(f"Created {len(self.worker_tasks)} worker task(s), awaiting...")

        if self.worker_tasks:
            # This supervisor runs until externally killed - nothing in
            # normal operation ever sets self._running back to False.
            # _rebalance_workers() (triggered concurrently by the config
            # watcher) cancels the tasks in self.worker_tasks and replaces
            # the list wholesale with fresh ones. A bare
            # `asyncio.gather(*self.worker_tasks)` here would capture a fixed
            # snapshot of the *original* tasks - once rebalance cancels them,
            # gather would raise CancelledError and kill the whole
            # orchestrator on every hot-reload. Loop forever instead,
            # re-reading self.worker_tasks each time so a rebalance's
            # replacement list gets picked up. Do NOT try to distinguish
            # "genuine exit" from "rebalance in progress" by comparing task
            # list identity - that races against _rebalance_workers()'s own
            # reassignment and can return before the new tasks are in place.
            while self._running:
                current_tasks = self.worker_tasks
                if not current_tasks:
                    await asyncio.sleep(1)
                    continue
                await asyncio.gather(*current_tasks, return_exceptions=True)
                # Yield briefly so a still-empty-or-unchanged worker_tasks
                # (e.g. all workers crashed with no rebalance pending)
                # doesn't spin the loop tightly.
                await asyncio.sleep(1)
        else:
            # Stay alive (heartbeat + config watcher keep running) instead of
            # exiting the process - an empty worker_definitions list means "no
            # safe default was known" (see worker.py's orchestrate command),
            # and exiting here would crash-loop the container instead of
            # idling until a real config arrives.
            logger.warning("No worker tasks created; idling (heartbeat/config-watch only).")
            await asyncio.Event().wait()

    async def get_cluster_health(self) -> List[Dict[str, Any]]:
        """
        Checks health of all Raspberry Pi workers.
        """
        import subprocess
        scaling = self.config.get("prospecting", {}).get("scaling", {})
        nodes = []
        for host_key in scaling.keys():
            if host_key != "fargate":
                # Nodes are reached over Tailscale by their bare machine name
                # (e.g. "cocli5x1") - a ".pi" suffix doesn't resolve at all.
                nodes.append({"host": host_key, "label": host_key.capitalize()})
        
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

    def resolve_worker_definitions(self, hostname: str, running_in_fargate: bool) -> List[Any]:
        """Resolves node config and returns a list of WorkerDefinitions for the host."""
        from ..models.campaigns.worker_config import WorkerDefinition
        from ..services.cluster_service import ClusterService

        cluster_service = ClusterService(self.campaign_name)
        node_config = next((n for n in cluster_service.get_nodes() if n.hostname.startswith(hostname)), None)

        if not node_config:
            if running_in_fargate or hostname == "fargate":
                scaling = cluster_service.config.get("prospecting", {}).get("scaling", {})
                fargate_scaling = scaling.get("fargate", {})
                if fargate_scaling:
                    worker_defs = []
                    for content_type, count in fargate_scaling.items():
                        if count > 0:
                            worker_defs.append(WorkerDefinition(
                                name=f"fargate-{content_type}",
                                role="full",
                                content_type=content_type,
                                workers=count,
                                iot_profile=None
                            ))
                    return worker_defs
                else:
                    return []
            else:
                # Default: 1 gm-list worker
                return [WorkerDefinition(name="default", role="full", content_type="gm-list", workers=1, iot_profile=None)]
        
        return node_config.workers

