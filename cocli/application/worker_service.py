# POLICY: frictionless-data-policy-enforcement
from __future__ import annotations
import socket
import asyncio
import json
import logging
import os
import time
from datetime import datetime, UTC
from typing import Any, Optional

from playwright.async_api import async_playwright, Browser, BrowserContext

from ..core.queue.factory import get_queue_manager
from ..core.error_classification import ErrorCategory, classify_exception
from ..scrapers.google.google_maps import scrape_google_maps
from ..models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem
from ..models.campaigns.queues.gm_details import GmItemTask
from ..models.campaigns.queues.base import QueueMessage
from ..models.campaigns.queues.enrichment import EnrichmentTask
from ..core.config import load_campaign_config
from ..core.paths import paths
from ..utils.playwright_utils import (
    launch_browser,
    new_details_context,
    new_enrichment_context,
)
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

# gm-list/pending/ is the real backlog signal, not a discovery-gen
# set-difference proxy for it - cocli audit scrape's stale-fallback
# "Gm List Pending" path and its "Gm List Claimed" lease count both read
# this directory's raw file count directly (see cocli/commands/audit.py),
# and pre-regression this was the whole point of GM_LIST_QUEUE_STATION's
# plain pending/completed contract. Mark, 2026-08-28: "we can dump them
# all in there at once ... it's just files" - a top-up copies in FULL (no
# limit), not a small perpetual watermark batch: gm-list's own poll()
# (FilesystemGmListQueue.poll()) is an early-terminating os.walk that
# stops as soon as it's leased one batch, so it doesn't care how many
# files sit in pending/ - a bigger backlog there costs nothing per-poll.
#
# Auto-triggering that top-up off "pending/ hit zero" was tried and
# PAUSED (commit a27b1b81) - draining to zero can't distinguish "more
# real work available" from "this batch is genuinely done." Superseded by
# an explicit ScrapeJobRun (cocli/models/campaigns/scrape_job_run.py,
# job_run_service.py) - only creating a run can ever cause a re-enqueue;
# this file's heartbeat loop only acts as a resilience backstop for a
# run that already exists (see the gm-list block in
# _compute_queue_pending()).


def _is_orphaned_playwright_future(context: dict[str, Any]) -> bool:
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
    campaign_name: str, context: dict[str, Any]
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

    def _handler(loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
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
    job_run_id: Optional[str] = None,
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

    job_run_id: propagated from the ScrapeTask that discovered this item
    (see cocli/models/campaigns/scrape_job_run.py) onto whichever
    downstream task gets created, so gm-details/enrichment completion can
    eventually be traced back to the run that found them.

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
            EnrichmentTask(
                domain=str(list_item.domain),
                company_slug=slugify(str(list_item.name) if list_item.name else ""),
                campaign_name=campaign_name,
                force_refresh=False,
                ack_token=None,
                job_run_id=job_run_id,
            )
        )
        prospect = transform_gm_list_item_to_google_maps_prospect(list_item)
        prospect.processed_by = processed_by
        ProspectsIndexManager(campaign_name).add_to_wal(prospect)
    else:
        gm_list_item_queue.push(
            list_item.to_task(campaign_name, force_refresh=False, job_run_id=job_run_id)
        )


class WorkerService:
    def __init__(self, campaign_name: str, processed_by: Optional[str] = None, role: str = "full"):
        self.campaign_name = campaign_name
        self.processed_by = processed_by or (os.getenv("COCLI_HOSTNAME") or socket.gethostname().split(".")[0])
        self.role = role
        self._load_config()
        self.worker_tasks: list[asyncio.Task[Any]] = []
        self.child_workers: list["WorkerService"] = []
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
        """Watches for config updates received via gossip and applies them.

        Applied (or rejected) update files are deleted immediately - not
        just tracked via an in-memory watermark. Production incident
        (2026-08): a plain `last_processed` local variable reset to 0 on
        every container restart while the on-disk files it tracked against
        (bind-mounted, so restart-durable) never got cleaned up - a single
        stale broadcast from months earlier kept getting silently
        reapplied on every hourly cron restart, indefinitely, since it was
        still the newest filename in a directory nothing new had arrived
        in. Live inspection (2026-08-12) found 9 such files on cocli5x0
        dating back to 2026-07-05, none ever processed away.

        Each file also carries the campaign_name it was broadcast for (see
        gossip_bridge.py). A file whose campaign doesn't match this
        container's own is rejected rather than applied - the write-side
        campaign filter in gossip_bridge.py is the primary guard against
        cross-campaign contamination, but a node physically reassigned
        between campaigns (this has happened: cocli5x0 was reassigned
        exclusively to turboship on 2026-08-08) can still carry old files
        from its prior campaign on the same bind-mounted data directory,
        and nothing on the read side used to check that.

        Only this node's own scaling stanza is merged into config.toml.
        The broadcast carries the whole cluster's scaling table so every
        node can pick its own slice out of one message, but blindly
        writing the whole table locally would silently overwrite (or
        resurrect) every other node's entry on every hot-reload.
        """
        from ..core.paths import paths
        update_dir = paths.root / "remote_updates"
        update_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"WorkerService: Watching for config updates in {update_dir}")

        hostname = self.processed_by.split("-")[0]

        while self._running:
            try:
                # Find the latest config file
                updates = sorted(update_dir.glob("config_*.json"))
                if updates:
                    latest = updates[-1]
                    # Format: config_TIMESTAMP.json
                    try:
                        int(latest.stem.split("_")[1])  # validate the name shape before acting on it
                        with open(latest, "r") as f:
                            payload = json.load(f)

                        file_campaign = payload.get("campaign_name") if isinstance(payload, dict) else None
                        new_scaling = payload.get("scaling") if isinstance(payload, dict) else None

                        if file_campaign is None or new_scaling is None:
                            logger.warning(
                                f"Discarding {latest.name}: legacy format with no campaign tag, "
                                "can't verify it's safe to apply."
                            )
                        elif file_campaign != self.campaign_name:
                            logger.warning(
                                f"Discarding {latest.name}: broadcast for campaign "
                                f"'{file_campaign}' != this node's '{self.campaign_name}'."
                            )
                        else:
                            config_path = paths.campaign(self.campaign_name).path / "config.toml"
                            if config_path.exists() and hostname in new_scaling:
                                logger.info(f"Applying hot config update from gossip: {latest.name}")
                                import toml
                                with open(config_path, "r") as f:
                                    full_config = toml.load(f)

                                # Merge just this node's own slice - never
                                # blindly replace the whole scaling table.
                                full_config.setdefault("prospecting", {}).setdefault("scaling", {})
                                full_config["prospecting"]["scaling"][hostname] = new_scaling[hostname]

                                with open(config_path, "w") as f:
                                    toml.dump(full_config, f)

                                logger.info(f"Local config.toml updated with gossip scaling for {hostname}.")
                                self._load_config()
                                await self._rebalance_workers()

                        # Applied, rejected, or config.toml didn't exist to
                        # apply it to - either way, this and any older
                        # superseded files must not survive to be replayed
                        # later.
                        for stale in updates:
                            stale.unlink(missing_ok=True)
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
            else:
                # Not just silence - a boot-time worker of this type is
                # about to be cancelled below and nothing will replace it.
                # Production incident (2026-08-11): gm-details sat at
                # scaling=0 on turboship for 6+ days, invisible because
                # this rebalance never logged anything a human or the
                # audit tool's "Starting worker:" parser could see.
                logger.info(f"Rebalance: {c_type} scaled to 0 on {hostname} - no worker will run.")
                # Also emit a properly-formatted line the audit's
                # "Starting worker:" regex actually matches (workers=0) -
                # otherwise cocli audit cluster would still show whatever
                # non-zero count was logged at boot for this content type,
                # since nothing would ever overwrite it.
                logger.info(f"Starting worker: {hostname}-{c_type} (type={c_type}, workers=0)")

        # Google Maps conclusively blocks Fargate/data-center IP ranges (see
        # CLAUDE.md "Known Issues") - the same hard rule
        # run_orchestrated_workers() enforces at startup; a hot-reload must
        # not be able to bypass it.
        running_in_fargate = bool(os.getenv("COCLI_RUNNING_IN_FARGATE"))

        # See _reclaim_expired_leases()'s docstring: a rebalance is exactly
        # the kind of event that leaves a cancelled worker's in-flight lease
        # behind, and this fires far more often than a full process restart.
        self._reclaim_expired_leases({wd.content_type for wd in worker_defs})

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

            # Same format run_orchestrated_workers() logs at boot - the
            # audit tool's "Starting worker:" regex is how `cocli audit
            # cluster`'s Workers column gets populated. Without this line
            # here too, that column only ever shows the pre-rebalance
            # boot-time count, silently stale the moment a rebalance
            # changes anything (see incident note above).
            logger.info(f"Starting worker: {wd.name} (type={wd.content_type}, workers={wd.workers})")

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
        return await launch_browser(playwright, headless=headless)

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
            tasks = await asyncio.to_thread(gm_list_queue.poll, batch_size=1)

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
                discovered_items: list[GoogleMapsListItem] = []
                # Keep track of Place IDs in this specific search to avoid redundant enqueuing
                pushed_place_ids: set[str] = set()

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
                            job_run_id=task.job_run_id,
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
                await asyncio.to_thread(gm_list_queue.ack, task)

                if once:
                    return
            except Exception as e:
                category = classify_exception(e)
                logger.error(f"Task Failed [{category.value}]: {e}")
                # Negative acknowledge on failure (removes lease, task stays available)
                await asyncio.to_thread(gm_list_queue.nack, task)

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
        logger.info("Details worker task loop entered.")
        while True:
            self.last_activity_ts = time.time()
            try:
                if not context.browser or not context.browser.is_connected():
                    logger.error("Details worker: browser is disconnected. Breaking task loop to restart.")
                    break
            except Exception as e:
                logger.error(f"Details worker: browser connectivity check failed: {e}")
                break

            tasks: list[GmItemTask] = await asyncio.to_thread(gm_list_item_queue.poll, batch_size=1)
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

                    if final_prospect_data is None:
                        # process() already logged and swallowed whatever went
                        # wrong (no data returned, or an internal exception) -
                        # it never reached add_to_wal(). Acking here anyway
                        # would mark the task "completed" in gm-details with
                        # no WAL entry ever written, permanently: nothing
                        # would retry it and nothing would ever notice.
                        # Production incident (2026-08): 21 place_ids stuck in
                        # exactly this state, found via `cocli index trace`.
                        logger.warning(
                            f"Detail Task produced no prospect data for {task.place_id} - "
                            "nacking for retry instead of acking an empty result."
                        )
                        await asyncio.to_thread(gm_list_item_queue.nack, task)
                    else:
                        if final_prospect_data.domain:
                            enrichment_queue.push(EnrichmentTask(domain=str(final_prospect_data.domain), company_slug=slugify(str(final_prospect_data.name) if final_prospect_data.name else ""), campaign_name=task.campaign_name, force_refresh=task.force_refresh, ack_token=None, job_run_id=task.job_run_id))

                        await asyncio.to_thread(gm_list_item_queue.ack, task)
                finally:
                    await page.close()
                if once:
                    return
            except Exception as e:
                category = classify_exception(e)
                if category in (ErrorCategory.NAVIGATION_FAILED, ErrorCategory.TIMEOUT):
                    logger.info(f"[{category.value}] Detail Task notice for {task.place_id}: {e}")
                else:
                    logger.error(f"Detail Task Failed [{category.value}]: {e}")
                await asyncio.to_thread(gm_list_item_queue.nack, task)
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
            try:
                if not context.browser or not context.browser.is_connected():
                    logger.error("Browser is disconnected. Breaking task loop to restart.")
                    break
            except Exception as e:
                logger.error(f"Enrichment worker: browser connectivity check failed: {e}")
                break

            tasks: list[QueueMessage] = await asyncio.to_thread(enrichment_queue.poll, batch_size=1)
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
                    from .company_service import update_company_from_website_data

                    await update_company_from_website_data(
                        company, website_data, campaign_obj
                    )
                if website_data and website_data.error:
                    # WebsiteScraper.run() catches its own Timeout/Exception
                    # internally and always returns a Website (see
                    # website_scraper.py run()'s except blocks) - a failed
                    # scrape never raises here, so acking unconditionally
                    # marked every failure "completed" with nothing to ever
                    # retry it. Mirror the gm-details worker's identical fix
                    # above (2026-08 incident: 21 place_ids stuck completed
                    # with no data, found via `cocli index trace`). The
                    # write above is already merge-safe (Website.save()), so
                    # this only changes queue disposition, not persistence.
                    err_cat = website_data.error_category
                    cat_val = err_cat.value if err_cat is not None else "unknown"
                    if err_cat in (ErrorCategory.NAVIGATION_FAILED, ErrorCategory.TIMEOUT):
                        logger.info(
                            f"[{cat_val}] Enrichment scrape notice for {task.domain}: "
                            f"{website_data.error} - nacking for retry."
                        )
                    else:
                        logger.warning(
                            f"Enrichment scrape failed for {task.domain} "
                            f"[{cat_val}]: {website_data.error} - "
                            "nacking for retry instead of acking a failed result."
                        )
                    await asyncio.to_thread(enrichment_queue.nack, task)
                else:
                    await asyncio.to_thread(enrichment_queue.ack, task)
                if once:
                    return
            except Exception as e:
                category = classify_exception(e)
                if category in (ErrorCategory.NAVIGATION_FAILED, ErrorCategory.TIMEOUT):
                    logger.info(f"[{category.value}] Enrichment Task notice for {task.domain}: {e}")
                else:
                    logger.error(f"Enrichment Task Failed [{category.value}]: {e}")
                await asyncio.to_thread(enrichment_queue.nack, task)
                if once:
                    return

                await asyncio.sleep(5)


    def _apply_wilderness_mark(
        self, tile_id: str, mark: bool, s3_client: Any
    ) -> None:
        """Write/delete the global wilderness-tile index and mirror to campaign S3."""
        from cocli.core.scrape_index import ScrapeIndex

        index = ScrapeIndex()
        if mark:
            local_path = index.mark_wilderness_tile(tile_id, marked_by="web")
        else:
            index.unmark_wilderness_tile(tile_id)
            local_path = index.wilderness_tile_path(tile_id)

        if s3_client is None or local_path is None:
            return
        parsed = tile_id.split("_")
        if len(parsed) < 2:
            return
        key = (
            f"campaigns/{self.campaign_name}/indexes/wilderness-tiles/"
            f"{local_path.parent.parent.name}/{local_path.parent.name}/{local_path.name}"
        )
        bucket = f"cocli-data-{self.campaign_name}"
        try:
            if mark and local_path.exists():
                s3_client.upload_file(str(local_path), bucket, key)
            else:
                s3_client.delete_object(Bucket=bucket, Key=key)
        except Exception:
            logger.exception("Failed to sync wilderness tile %s to S3", tile_id)

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
                    elif "unmark-wilderness" in cmd.command:
                        idx = parts.index("unmark-wilderness")
                        if idx + 1 < len(parts):
                            await asyncio.to_thread(
                                self._apply_wilderness_mark,
                                parts[idx + 1],
                                False,
                                s3_client,
                            )
                    elif "mark-wilderness" in cmd.command:
                        idx = parts.index("mark-wilderness")
                        if idx + 1 < len(parts):
                            await asyncio.to_thread(
                                self._apply_wilderness_mark,
                                parts[idx + 1],
                                True,
                                s3_client,
                            )
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
                    tasks: list[asyncio.Task[Any]] = [asyncio.create_task(c) for c in coros]
                    
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
                    context = await new_details_context(browser)
                    s3_client = self.get_s3_client()
                    details_q = get_queue_manager("details", use_cloud=True, queue_type="gm_list_item", campaign_name=self.campaign_name, s3_client=s3_client)
                    enrich_q = get_queue_manager("enrichment", use_cloud=True, queue_type="enrichment", campaign_name=self.campaign_name, s3_client=s3_client)
                    coros = [self._run_details_task_loop(context, details_q, enrich_q, s3_client, debug, once) for _ in range(workers)]
                    tasks: list[asyncio.Task[Any]] = [asyncio.create_task(c) for c in coros]
                    
                    while time.time() - session_start < max_session_duration_s:
                        done, pending = await asyncio.wait(tasks, timeout=30, return_when=asyncio.FIRST_EXCEPTION)
                        if once:
                            break
                        # Check if any task crashed - previously unlogged, so a
                        # crashed details worker looked identical to a clean
                        # "Recycling..." session end in the logs (see
                        # task-agent ticket
                        # turboship-gm-details-worker-silently-dies-every-restart-never-polls).
                        for t in done:
                            if t.exception():
                                logger.error(f"Details worker task crashed: {t.exception()}")
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
                    context = await new_enrichment_context(browser)
                    s3_client = self.get_s3_client()
                    enrich_q = get_queue_manager("enrichment", use_cloud=True, queue_type="enrichment", campaign_name=self.campaign_name, s3_client=s3_client)
                    coros = [self._run_enrichment_task_loop(context, enrich_q, debug, once, s3_client) for _ in range(workers)]
                    tasks: list[asyncio.Task[Any]] = [asyncio.create_task(c) for c in coros]
                    
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



    async def _compute_queue_pending(self) -> dict[str, int]:
        """Live pending counts for this node's own local queues.

        The audit machine's own local disk is never a faithful mirror of
        pending/ - PiSyncService only ever syncs completed/ (see task-agent
        ticket scrape-pipeline-audit-tables-pending-counts-read-stale-local-dev-machine-queue-dirs-not-live-pi-state).
        This node is the one place these numbers can be computed correctly
        (it's reading its own disk), so it publishes them via the heartbeat
        instead of leaving the audit machine to guess from a stale mirror.

        Runs on a background thread since count_state()/reconcile can walk
        thousands of files - not something the heartbeat's event loop
        should block on while scrape/detail/enrichment loops are running
        concurrently.
        """
        from ..core.queue.factory import get_queue_manager
        from .gm_list_enqueue_service import enqueue_unscraped_to_gm_list_pending

        def _compute() -> dict[str, int]:
            result: dict[str, int] = {}
            try:
                gm_details_q = get_queue_manager(
                    "gm-details", queue_type="gm_list_item", campaign_name=self.campaign_name
                )
                result["gm-details"] = gm_details_q.count_state("pending")
            except Exception as e:
                logger.debug(f"queue_pending: gm-details count failed: {e}")
            try:
                enrichment_q = get_queue_manager(
                    "enrichment", queue_type="enrichment", campaign_name=self.campaign_name
                )
                result["enrichment"] = enrichment_q.count_state("pending")
            except Exception as e:
                logger.debug(f"queue_pending: enrichment count failed: {e}")
            try:
                # Job-run poller: resilience backstop + completion marking,
                # NOT the trigger for topping up gm-list/pending/ - only an
                # explicit ScrapeJobRun (job_run_service.create_job_run(),
                # called from cocli dev process-map-tile or a future
                # requeue process) can ever cause that. gm-list/pending/
                # draining to zero is never itself a trigger - see
                # cocli/models/campaigns/scrape_job_run.py for why a blind
                # pending==0 trigger is wrong (commit a27b1b81 paused the
                # previous attempt at one). This just (a) retries a run's
                # own copy if the process that created it crashed between
                # discovery_gen_completed_at and started_at, and (b) marks
                # gm_list_completed_at once a run's identities are all
                # resolved.
                from .job_run_service import (
                    check_and_mark_gm_list_completed,
                    enqueue_gm_list_for_run,
                    list_open_job_runs,
                )

                for run in list_open_job_runs(self.campaign_name):
                    if run.started_at is None:
                        enqueue_gm_list_for_run(run)
                    else:
                        check_and_mark_gm_list_completed(run)
            except Exception as e:
                logger.debug(f"queue_pending: job-run poller failed: {e}")
            try:
                # Campaign-wide "how much unscraped backlog exists" figure
                # - independent of job-run tracking above, always dry-run
                # (report-only). This never copies anything itself.
                gm_list_result = enqueue_unscraped_to_gm_list_pending(
                    campaign_name=self.campaign_name, dry_run=True
                )
                result["gm-list"] = gm_list_result.candidates
            except Exception as e:
                logger.debug(f"queue_pending: gm-list count failed: {e}")
            return result

        return await asyncio.to_thread(_compute)

    async def _compute_gm_list_tile_coverage(self) -> dict[str, int]:
        """Deduplicated (lat,lon) tile-level gm-list coverage.

        Distinct from _compute_queue_pending()'s gm-list figure, which is
        (tile, search-phrase) granularity - this is the "how many actual
        map tiles still have zero coverage" question cocli audit scrape's
        staged_active_tiles/completed_scraped_tiles/pending_scraped_tiles
        fields exist to answer.

        Uses the .json completion RECEIPT under gm-list/completed/results
        as the "this tile+phrase was attempted" signal, not .usv presence -
        a tile+phrase that legitimately found zero businesses still gets a
        receipt but never gets a .usv file (no items to write), so counting
        .usv presence silently undercounts real completions. Confirmed
        production bug 2026-08-16: cocli audit scrape reported 255 tiles
        pending (via .usv presence, on this dev machine's stale local
        mirror) when the live, receipt-based count on the Pi itself was 2.
        """
        from pathlib import Path

        from ..core.paths import paths

        def _compute() -> dict[str, int]:
            campaign_paths = paths.campaign(self.campaign_name)
            dg_root = campaign_paths.queue("discovery-gen").completed
            gm_list_root = campaign_paths.queue("gm-list").completed / "results"

            def _tile_set(root: Path, pattern: str) -> set[str]:
                tiles: set[str] = set()
                if not root.exists():
                    return tiles
                for f in root.rglob(pattern):
                    parts = f.relative_to(root).parts
                    if len(parts) >= 3:
                        tiles.add(f"{parts[-3]}/{parts[-2]}")
                return tiles

            staged = _tile_set(dg_root, "*.usv")
            completed = _tile_set(gm_list_root, "*.json")
            return {
                "staged_tiles": len(staged),
                "tiles_with_any_result": len(completed),
                "tiles_with_zero_results": len(staged - completed),
            }

        return await asyncio.to_thread(_compute)

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
        designation: dict[str, int] = {}
        last_activity: dict[str, str] = {}
        for child in self.child_workers:
            if not child.content_type:
                continue
            designation[child.content_type] = designation.get(child.content_type, 0) + child.worker_count
            if child.last_activity_ts is not None:
                ts_iso = datetime.fromtimestamp(child.last_activity_ts, UTC).isoformat()
                if child.content_type not in last_activity or ts_iso > last_activity[child.content_type]:
                    last_activity[child.content_type] = ts_iso

        worker_count = sum(designation.values())
        now_iso = datetime.now(UTC).isoformat()

        stats = {
            "timestamp": now_iso,
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
            "queue_pending": {},
            "gm_list_tile_coverage": {},
        }

        # 1. Immediate local heartbeat & Gossip broadcast (<1ms, before any disk scans)
        try:
            with open("/tmp/cocli_heartbeat.json", "w") as f:
                json.dump(stats, f)
        except Exception as local_err:
            logger.debug(f"Failed to write local heartbeat: {local_err}")

        if bridge and bridge.running:
            try:
                from ..core.environment import get_environment
                hb = HeartbeatDatagram(
                    campaign_name=self.campaign_name,
                    node_id=self.processed_by,
                    timestamp=now_iso,
                    load_avg=cpu_usage,
                    memory_percent=mem_usage,
                    worker_count=worker_count,
                    active_tasks=worker_count,
                    environment=get_environment().value
                )
                bridge.broadcast_msg(hb.to_usv())
            except Exception as gossip_err:
                logger.debug(f"Gossip Heartbeat failed: {gossip_err}")

        # 2. Async heavy stats with strict 2s timeout so large queue dirs never block heartbeat loop
        try:
            stats["queue_pending"] = await asyncio.wait_for(self._compute_queue_pending(), timeout=2.0)
        except (asyncio.TimeoutError, Exception) as err:
            logger.debug(f"queue_pending calculation timed out or failed: {err}")

        try:
            stats["gm_list_tile_coverage"] = await asyncio.wait_for(self._compute_gm_list_tile_coverage(), timeout=2.0)
        except (asyncio.TimeoutError, Exception) as err:
            logger.debug(f"gm_list_tile_coverage calculation timed out or failed: {err}")

        # Update local copy & S3 put with completed stats
        try:
            with open("/tmp/cocli_heartbeat.json", "w") as f:
                json.dump(stats, f)
        except Exception:
            pass

        # Durability Tier (S3)
        try:
            s3_client.put_object(Bucket=self.bucket_name, Key=paths.s3.heartbeat(self.processed_by), Body=json.dumps(stats), ContentType="application/json")
        except Exception as s3_err:
            logger.debug(f"S3 Heartbeat failed: {s3_err}")

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

    def _reclaim_expired_leases(self, content_types: set[str]) -> None:
        """Reclaims leases abandoned by a previous crashed/killed worker
        before new workers of these content types start claiming. Without
        this, a worker that dies mid-task leaves its lease.json sitting in
        pending/ indefinitely - it doesn't block new claims on OTHER items,
        but it silently accumulates (roadmap had ~5,950 expired gm-list
        leases after ~6 months with no supervisor running) and previously
        required a manual `cocli audit queue purge-leases` to notice or fix.
        Safe to call at any time, from any call site: purge_expired_leases
        only removes leases whose heartbeat is already past
        max_heartbeat_age_minutes, so it can never touch a lease an
        actually-alive worker (this node or another) is still refreshing.
        Called from both run_orchestrated_workers() (full process boot) and
        _rebalance_workers() (config/scaling hot-reload) - a supervisor can
        run for a long time without a full restart, rebalancing many times
        as scaling config changes, so startup alone isn't "automatic
        enough" (Mark, 2026-08-30)."""
        from ..services.lease_cleanup import purge_expired_leases

        for content_type in content_types:
            queue_dir = paths.campaign(self.campaign_name).queue(content_type).pending
            metrics = purge_expired_leases(queue_dir, max_heartbeat_age_minutes=30)
            if metrics["leases_deleted"]:
                logger.info(
                    f"  Reclaimed {metrics['leases_deleted']} expired {content_type} "
                    f"lease(s) (found={metrics['leases_found']})"
                )

    async def run_orchestrated_workers(self, worker_definitions: list[Any], headless: bool = True, debug: bool = False) -> None:
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

        try:
            s3_client = self.get_s3_client()
            command_queue = get_queue_manager(
                "command",
                use_cloud=True,
                queue_type="command",
                campaign_name=self.campaign_name,
                s3_client=s3_client,
            )
            asyncio.create_task(
                self._run_command_poller_loop(command_queue, s3_client)
            )
            logger.info("Command poller started (mark-wilderness / config commands)")
        except Exception:
            logger.exception("Could not start command poller")

        logger.info(f"Orchestrating {len(worker_definitions)} worker definition(s)")

        # Google Maps conclusively blocks Fargate/data-center IP ranges (see
        # CLAUDE.md "Known Issues"). This is a hard rule, not just a missing-
        # config fallback: regardless of what config.toml says, gm-list/
        # gm-details must never be launched on Fargate.
        running_in_fargate = bool(os.getenv("COCLI_RUNNING_IN_FARGATE"))

        self._reclaim_expired_leases({wd.content_type for wd in worker_definitions})

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

    async def get_cluster_health(self) -> list[dict[str, Any]]:
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

    def resolve_worker_definitions(self, hostname: str, running_in_fargate: bool) -> list[Any]:
        """Resolves node config and returns a list of WorkerDefinitions for the host."""
        from ..models.campaigns.worker_config import WorkerDefinition
        from ..services.cluster_service import ClusterService

        cluster_service = ClusterService(self.campaign_name)
        node_config = next(
            (
                n
                for n in cluster_service.get_nodes()
                if n.hostname.lower().startswith(hostname.lower())
                or hostname.lower().startswith(n.hostname.lower())
            ),
            None,
        )

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

