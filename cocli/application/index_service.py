"""Index orchestration services for compaction, status, domain backfill, and datapackages.

Domain/orchestration layer (product-specific). No Rich/console presentation —
callers format Intermediate artifacts (status reports, compact results) for CLI/TUI.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Type

from pydantic import BaseModel, Field

from cocli.core.paths import paths
from cocli.models.base import BaseUsvModel, SchemaConflictError

logger = logging.getLogger(__name__)

LogCallback = Callable[[str], None]


def _emit(log_callback: Optional[LogCallback], message: str) -> None:
    """Forward a progress/status line to the caller without presentation coupling."""
    logger.info(message)
    if log_callback is not None:
        log_callback(message)


class IndexLockStatus(BaseModel):
    """Lock tier of a sharded index status report."""

    active: bool = False
    run_id: Optional[str] = None
    created_at: Optional[str] = None
    host: Optional[str] = None
    error: Optional[str] = None


class IndexCheckpointStatus(BaseModel):
    """Checkpoint (cold) tier of a sharded index status report."""

    found: bool = False
    size_mb: Optional[float] = None
    last_modified: Optional[str] = None
    error: Optional[str] = None


class IndexStatusReport(BaseModel):
    """Intermediate artifact: status of WAL / processing / checkpoint tiers."""

    campaign_name: str
    index_name: str
    lock: IndexLockStatus = Field(default_factory=IndexLockStatus)
    wal_backlog_count: int = 0
    processing_file_count: int = 0
    checkpoint: IndexCheckpointStatus = Field(default_factory=IndexCheckpointStatus)


class CompactResult(BaseModel):
    """Result of a Freeze-Ingest-Merge-Commit compaction workflow."""

    campaign_name: str
    index_name: str
    success: bool
    recovered_runs: List[str] = Field(default_factory=list)
    isolated_files: int = 0
    message: str = ""
    log_file: Optional[Path] = None


class DomainBackfillResult(BaseModel):
    """Result of backfilling the domain index from local enrichment files."""

    campaign_name: str
    tag: str
    records_added: int = 0
    compacted: bool = False
    message: str = ""


class WriteDatapackageResult(BaseModel):
    """Result of writing a Frictionless datapackage.json for an index."""

    index_name: str
    target_dir: Path
    resource_name: str
    resource_path: str
    message: str = ""


class ProspectTraceRow(BaseModel):
    """One identity's state across every station of the prospects pipeline."""

    place_id: str
    gm_list: str
    gm_details: str
    pi_wal: str
    checkpoint: str
    enrichment: str
    verdict: str
    gap_category: str


class ProspectTraceResult(BaseModel):
    """Result of tracing a batch of place_ids through the prospects pipeline."""

    campaign_name: str
    index_name: str
    rows: List[ProspectTraceRow] = Field(default_factory=list)


class RequeueRow(BaseModel):
    """Result of attempting to requeue one stuck place_id for gm-details."""

    place_id: str
    status: str  # "requeued" | "not_found" | "ssh_error"
    detail: str = ""


class RequeueResult(BaseModel):
    """Result of a requeue-stuck-details run across a batch of place_ids."""

    campaign_name: str
    index_name: str
    rows: List[RequeueRow] = Field(default_factory=list)


class PurgeInvalidPlaceIdsResult(BaseModel):
    """Result of purge_invalid_place_ids."""

    campaign_name: str
    index_name: str
    dry_run: bool
    removed_place_ids: List[str] = Field(default_factory=list)
    checkpoint_before: int = 0
    checkpoint_after: int = 0


class ArchiveWalNodeResult(BaseModel):
    """One node's outcome from archive_incomplete_schema_wal."""

    hostname: str
    archived: int = 0
    kept: int = 0
    error: str = ""


class ArchiveWalResult(BaseModel):
    """Result of archiving WAL records that don't match the current full
    schema (fewer fields than required_field_count)."""

    campaign_name: str
    index_name: str
    required_field_count: int
    dry_run: bool
    nodes: List[ArchiveWalNodeResult] = Field(default_factory=list)

    @property
    def total_archived(self) -> int:
        return sum(n.archived for n in self.nodes)

    @property
    def total_kept(self) -> int:
        return sum(n.kept for n in self.nodes)


class IndexService:
    """Application service for index lifecycle operations."""

    def __init__(self, campaign_name: str):
        self.campaign_name = campaign_name

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self, index_name: str = "google_maps_prospects") -> IndexStatusReport:
        """Collect WAL / processing / checkpoint status for a sharded index."""
        from cocli.core.compact import CompactManager

        manager = CompactManager(
            campaign_name=self.campaign_name, index_name=index_name
        )
        report = IndexStatusReport(
            campaign_name=self.campaign_name, index_name=index_name
        )

        # 1. Lock
        try:
            lock_obj = manager.s3.get_object(
                Bucket=manager._bucket, Key=manager.s3_lock_key
            )
            lock_data = json.loads(lock_obj["Body"].read().decode("utf-8"))
            report.lock = IndexLockStatus(
                active=True,
                run_id=lock_data.get("run_id"),
                created_at=lock_data.get("created_at"),
                host=lock_data.get("host"),
            )
        except manager.s3.exceptions.NoSuchKey:
            report.lock = IndexLockStatus(active=False)
        except Exception as e:
            logger.warning("Error checking index lock: %s", e)
            report.lock = IndexLockStatus(active=False, error=str(e))

        # 2. WAL backlog
        wal_count = 0
        paginator = manager.s3.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=manager._bucket, Prefix=manager.s3_wal_prefix)
        for page in pages:
            if "Contents" in page:
                wal_count += len(
                    [
                        obj
                        for obj in page["Contents"]
                        if obj["Key"].endswith((".usv", ".csv"))
                    ]
                )
        report.wal_backlog_count = wal_count

        # 3. Processing (staging)
        proc_prefix = manager.s3_index_prefix + "processing/"
        proc_count = 0
        for page in paginator.paginate(Bucket=manager._bucket, Prefix=proc_prefix):
            if "Contents" in page:
                proc_count += len(page["Contents"])
        report.processing_file_count = proc_count

        # 4. Checkpoint
        checkpoint_key = manager.s3_index_prefix + manager.checkpoint_filename

        try:
            head = manager.s3.head_object(Bucket=manager._bucket, Key=checkpoint_key)
            size_mb = head["ContentLength"] / 1024 / 1024
            last_modified = head["LastModified"].strftime("%Y-%m-%d %H:%M:%S")
            report.checkpoint = IndexCheckpointStatus(
                found=True, size_mb=size_mb, last_modified=last_modified
            )
        except manager.s3.exceptions.NoSuchKey:
            report.checkpoint = IndexCheckpointStatus(found=False)
        except Exception as e:
            logger.warning("Error checking checkpoint: %s", e)
            report.checkpoint = IndexCheckpointStatus(found=False, error=str(e))

        return report

    # ------------------------------------------------------------------
    # Compact (FIMC)
    # ------------------------------------------------------------------

    def list_interrupted_runs(
        self, index_name: str = "google_maps_prospects"
    ) -> List[str]:
        """List run_ids under processing/ on S3 (interrupted compact runs)."""
        from cocli.core.compact import CompactManager

        manager = CompactManager(
            campaign_name=self.campaign_name, index_name=index_name
        )
        paginator = manager.s3.get_paginator("list_objects_v2")
        proc_prefix = manager.s3_index_prefix + "processing/"
        pages = paginator.paginate(
            Bucket=manager._bucket, Prefix=proc_prefix, Delimiter="/"
        )

        interrupted_runs: List[str] = []
        for page in pages:
            if "CommonPrefixes" in page:
                for cp in page["CommonPrefixes"]:
                    interrupted_run_id = cp["Prefix"].split("/")[-2]
                    interrupted_runs.append(interrupted_run_id)
        return interrupted_runs

    def recover_interrupted_run(
        self,
        index_name: str,
        run_id: str,
        log_file: Optional[Path] = None,
    ) -> None:
        """Complete an interrupted compact run (ingest → merge → commit → cleanup)."""
        from cocli.core.compact import CompactManager

        manager = CompactManager(
            campaign_name=self.campaign_name,
            index_name=index_name,
            log_file=log_file,
        )
        logger.info("Recovering interrupted run: %s", run_id)
        manager.run_id = run_id
        manager.s3_proc_prefix = manager.s3_index_prefix + f"processing/{run_id}/"
        manager.local_proc_dir = manager.index_dir / "processing" / run_id
        manager.acquire_staging()
        manager.merge()
        manager.commit_remote()
        manager.cleanup()

    def compact(
        self,
        index_name: str = "google_maps_prospects",
        log_file: Optional[Path] = None,
        log_callback: Optional[LogCallback] = None,
    ) -> CompactResult:
        """
        Compact WAL into the main checkpoint (Freeze-Ingest-Merge-Commit).

        Self-heals interrupted runs first, then runs a full compact cycle under lock.
        ``log_callback`` receives plain step messages so CLI/TUI can show live progress
        without the service depending on Rich.
        """
        from cocli.core.compact import CompactManager

        _emit(log_callback, "Checking for interrupted runs...")
        recovered = self.list_interrupted_runs(index_name)
        if recovered:
            _emit(
                log_callback,
                f"Found {len(recovered)} interrupted runs. Recovering...",
            )
            for run_id in recovered:
                _emit(log_callback, f"Recovering interrupted run: {run_id}")
                try:
                    self.recover_interrupted_run(index_name, run_id, log_file=log_file)
                except Exception as e:
                    logger.error(
                        "Failed to recover interrupted run %s: %s", run_id, e, exc_info=True
                    )
                    msg = f"Failed to recover interrupted run {run_id}: {e}"
                    _emit(log_callback, msg)
                    return CompactResult(
                        campaign_name=self.campaign_name,
                        index_name=index_name,
                        success=False,
                        recovered_runs=recovered,
                        message=msg,
                        log_file=log_file,
                    )
            _emit(log_callback, "Recovery complete.")
        else:
            _emit(log_callback, "No interrupted runs found.")

        manager = CompactManager(
            campaign_name=self.campaign_name,
            index_name=index_name,
            log_file=log_file,
        )

        from cocli.services.cluster_service import ClusterService
        try:
            nodes = ClusterService(self.campaign_name).get_nodes()
        except Exception as e:
            logger.warning("Could not resolve cluster nodes for %s: %s", self.campaign_name, e)
            nodes = []

        _emit(log_callback, "Acquiring S3 lock...")
        if not manager.acquire_lock():
            msg = "Lock acquisition failed (another compact may be running)."
            _emit(log_callback, msg)
            return CompactResult(
                campaign_name=self.campaign_name,
                index_name=index_name,
                success=False,
                recovered_runs=recovered,
                message=msg,
                log_file=log_file,
            )
        _emit(log_callback, "Lock acquired.")

        try:
            if index_name == "google_maps_prospects":
                # gm-list already captures category/phone/rating/reviews_count/
                # street_address reliably (see task-agent
                # wire-gm-list-data-into-prospects-compaction-deprioritize-
                # gm-details) - COALESCE(gm_list.field, checkpoint.field) only
                # ever fills a gap or refreshes, never blanks a good value, so
                # this is safe to run on every compact. Was previously a
                # separate manual step (`cocli data queue compact gm-list`)
                # that ran exactly once (2026-06-29) and was never automated -
                # confirmed live 2026-08-21 against turboship, real gm-list
                # data on disk was never reaching most of the checkpoint.
                #
                # Deliberately does not affect the moved == 0 short-circuit
                # below: this just updates the local checkpoint file as a
                # best-effort side step. If a run has no new WAL either, the
                # gm-list-recovered data isn't lost - it's already sitting in
                # the checkpoint file and rides along as a retained input on
                # the next real compact. Forcing an extra S3 commit on every
                # gm-list merge (even a no-op one) was considered and
                # rejected as more invasive than necessary.
                _emit(log_callback, "Merging gm-list results into checkpoint...")
                try:
                    from cocli.core.transformers.gm_list_to_checkpoint import (
                        compact_gm_list_results,
                    )

                    gm_list_merged = compact_gm_list_results(self.campaign_name)
                    _emit(log_callback, f"gm-list merge: {gm_list_merged} records.")
                except Exception as e:
                    logger.warning(
                        "gm-list merge failed for %s: %s", self.campaign_name, e
                    )
                    _emit(log_callback, f"gm-list merge failed (continuing): {e}")

            _emit(log_callback, "Staging Pi WAL over Tailscale...")
            moved = manager.isolate_wal(nodes=nodes)
            if moved == 0:
                msg = "Nothing to compact."
                _emit(log_callback, msg)
                return CompactResult(
                    campaign_name=self.campaign_name,
                    index_name=index_name,
                    success=True,
                    recovered_runs=recovered,
                    isolated_files=0,
                    message=msg,
                    log_file=log_file,
                )
            _emit(log_callback, f"Staged {moved} files.")

            _emit(
                log_callback,
                "Merging via stations commit path (DuckDB fold + CURRENT CAS)...",
            )
            manager.merge()
            _emit(log_callback, "Merge complete (CURRENT + prospects.usv).")

            _emit(log_callback, "Uploading new checkpoint to S3...")
            manager.commit_remote()
            _emit(log_callback, "S3 Checkpoint updated.")

            _emit(log_callback, "Cleaning up...")
            manager.cleanup()
            _emit(log_callback, "Cleanup complete.")

            msg = "Compaction workflow finished successfully."
            return CompactResult(
                campaign_name=self.campaign_name,
                index_name=index_name,
                success=True,
                recovered_runs=recovered,
                isolated_files=moved,
                message=msg,
                log_file=log_file,
            )
        except Exception as e:
            logger.error("Compaction failed: %s", e, exc_info=True)
            msg = f"Compaction failed: {e}"
            _emit(log_callback, msg)
            return CompactResult(
                campaign_name=self.campaign_name,
                index_name=index_name,
                success=False,
                recovered_runs=recovered,
                message=msg,
                log_file=log_file,
            )
        finally:
            manager.release_lock()

    # ------------------------------------------------------------------
    # Trace (identity-scoped audit across pipeline stations)
    # ------------------------------------------------------------------

    def _fetch_pi_wal_ids(self, index_name: str) -> set[str]:
        """One SSH round-trip per Pi node, not one per identity."""
        import subprocess

        from cocli.services.cluster_service import ClusterService

        ids: set[str] = set()
        try:
            nodes = ClusterService(self.campaign_name).get_nodes()
        except Exception as e:
            logger.warning("Could not resolve cluster nodes for %s: %s", self.campaign_name, e)
            return ids

        for node in nodes:
            target = node.ip_address or node.hostname
            remote_path = f"repos/data/campaigns/{self.campaign_name}/indexes/{index_name}/wal"
            try:
                result = subprocess.run(
                    [
                        "ssh", "-o", "ConnectTimeout=10", f"mstouffer@{target}",
                        f"find {remote_path} -name '*.usv' -printf '%f\\n' 2>/dev/null",
                    ],
                    capture_output=True, text=True, timeout=30,
                )
            except subprocess.TimeoutExpired:
                logger.warning("WAL listing on %s timed out - skipping.", node.hostname)
                continue
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line.endswith(".usv"):
                        ids.add(line[: -len(".usv")])
        return ids

    def discover_all_place_ids(self, index_name: str = "google_maps_prospects") -> List[str]:
        """Every place_id this campaign has ever touched - the seed set for
        a whole-campaign traceability audit (as opposed to a caller-supplied
        list for targeted debugging).

        Union of gm-list's current discovery results, the checkpoint's own
        identities, AND the Pi WAL's identities - no single source is
        sufficient on its own. Confirmed live 2026-08-18 twice, each time
        making a "0 gaps found" audit result untrustworthy until fixed:
        (1) turboship - some checkpoint entries have no corresponding
        *current* gm-list result file (gm-list's completed/results/ tree
        doesn't retain everything forever), so gm-list alone under-counted.
        (2) roadmap - far more severe: its checkpoint has never been
        compacted at all (doesn't exist, on this machine OR on its own Pi
        node), while its WAL held 31,821 real records - gm-list ∪ checkpoint
        alone found only 3,788 identities, an ~88% undercount, silently
        making a campaign with a near-total compaction failure look almost
        entirely healthy.
        """
        from cocli.core.prospect_trace import CheckpointPresenceCheck, GmListResultsCheck
        from cocli.core.prospects_csv_manager import ProspectsIndexManager

        campaign_paths = paths.campaign(self.campaign_name)
        gm_list_results_dir = campaign_paths.queue("gm-list").completed / "results"
        checkpoint_path = ProspectsIndexManager(self.campaign_name).checkpoint_path

        gm_list_ids = GmListResultsCheck(gm_list_results_dir).all_identities()
        checkpoint_ids = CheckpointPresenceCheck(checkpoint_path).all_identities()
        wal_ids = self._fetch_pi_wal_ids(index_name)
        return sorted(gm_list_ids | checkpoint_ids | wal_ids)

    def trace_prospects(
        self, place_ids: List[str], index_name: str = "google_maps_prospects"
    ) -> ProspectTraceResult:
        """Trace each place_id across gm-list -> gm-details -> Pi WAL ->
        checkpoint -> enrichment, reporting where (if anywhere) its trail
        goes cold.

        Built from the ad hoc investigation of a 2026-08-13 incident where a
        fresh compaction dropped previously-qualifying prospects. See
        cocli/core/prospect_trace.py for the reusable station-check
        mechanism this is assembled from, and its docstring for why this
        exists alongside (not instead of) stations' own `stations inspect`.

        The enrichment hop is keyed by domain, not place_id (see
        ProspectDomainIndex's docstring for why) - resolved per-row after
        the other four checks, only for rows that made it to checkpoint.
        """
        from cocli.core.prospect_trace import (
            CheckpointPresenceCheck,
            GmListResultsCheck,
            PrebuiltSetCheck,
            ProspectDomainIndex,
            QueueBucketCheck,
            StationCheck,
            StationResult,
            categorize_verdict,
            diagnose_prospect_trace,
            trace_identities,
        )
        from cocli.core.prospects_csv_manager import ProspectsIndexManager

        campaign_paths = paths.campaign(self.campaign_name)
        gm_list_results_dir = campaign_paths.queue("gm-list").completed / "results"
        gm_details_queue = campaign_paths.queue("gm-details")
        enrichment_queue = campaign_paths.queue("enrichment")
        checkpoint_path = ProspectsIndexManager(self.campaign_name).checkpoint_path
        wal_root = paths.campaign(self.campaign_name).index(index_name).wal

        wal_ids = self._fetch_pi_wal_ids(index_name)

        checks: List[StationCheck] = [
            GmListResultsCheck(gm_list_results_dir),
            QueueBucketCheck(
                "gm-details",
                gm_details_queue.completed,
                gm_details_queue.pending,
                gm_details_queue.path / "failed",
            ),
            PrebuiltSetCheck("pi-wal", wal_ids),
            CheckpointPresenceCheck(checkpoint_path),
        ]
        enrichment_check = QueueBucketCheck(
            "enrichment",
            enrichment_queue.completed,
            enrichment_queue.pending,
            enrichment_queue.path / "failed",
        )
        domain_index = ProspectDomainIndex(checkpoint_path, wal_root)

        rows: List[ProspectTraceRow] = []
        for trace_row in trace_identities(checks, place_ids):
            r = trace_row.results
            gm_list_result = r["gm-list"]
            gm_list_display = (
                f"{gm_list_result.state} ({gm_list_result.detail})"
                if gm_list_result.detail
                else gm_list_result.state
            )

            enrichment_result: Optional[StationResult] = None
            if r["checkpoint"].state == "present":
                domain = domain_index.get_domain(trace_row.identity)
                if not domain:
                    enrichment_result = StationResult(station="enrichment", state="no domain")
                else:
                    enrichment_result = enrichment_check.check(domain)

            verdict = diagnose_prospect_trace(r, enrichment=enrichment_result)
            rows.append(
                ProspectTraceRow(
                    place_id=trace_row.identity,
                    gm_list=gm_list_display,
                    gm_details=r["gm-details"].state,
                    pi_wal=r["pi-wal"].state,
                    checkpoint=r["checkpoint"].state,
                    enrichment=enrichment_result.state if enrichment_result else "n/a",
                    verdict=verdict,
                    gap_category=categorize_verdict(verdict),
                )
            )

        return ProspectTraceResult(
            campaign_name=self.campaign_name, index_name=index_name, rows=rows
        )

    # ------------------------------------------------------------------
    # Requeue (recover gm-details tasks acked with no WAL entry)
    # ------------------------------------------------------------------

    def requeue_stuck_details(
        self, place_ids: List[str], index_name: str = "google_maps_prospects"
    ) -> RequeueResult:
        """Recover gm-details tasks that were acked with no real output (the
        gm-details-acks-unconditionally incident, fixed in worker_service.py's
        _run_details_task_loop): reconstruct a fresh task and push it back
        onto the queue for a retry.

        The stale completed/{place_id}.json marker left behind by the bug is
        itself the original GmItemTask - ack() moved it there verbatim - and
        PiSyncService._SYNC_QUEUES already syncs gm-details/completed/ from
        every Pi node to this machine, so it's read locally as the primary
        source (exact, no reconstruction). Only falls back to a gm-list
        result row (cocli/core/prospect_trace.py:find_gm_list_rows) for the
        rare case where no local completed marker exists.

        Must write the fresh pending task directly to a Pi node's filesystem
        over SSH, not locally: pending/ is never synced in either direction
        (only completed/ is), so a local FilesystemGmDetailsQueue.push()
        would write to a directory no worker ever polls.

        Pushes the fresh task to exactly one node - every enabled node polls
        the same gm-details queue directory shape, so pushing to all of them
        would have N nodes race to scrape the same place_id and write N WAL
        entries for it. The stale completed marker, by contrast, is cleared
        on every node, since we don't know which one produced it - and only
        after the pending task write is confirmed, mirroring the C9
        source-deletion-after-commit discipline used elsewhere in this
        pipeline: never remove the only trace of a stuck record before its
        replacement is safely in place.
        """
        import json
        import shlex
        import subprocess

        from pydantic import ValidationError

        from cocli.core.prospect_trace import find_gm_list_rows
        from cocli.core.sharding import get_place_id_shard
        from cocli.models.campaigns.queues.gm_details import GmItemTask
        from cocli.services.cluster_service import ClusterService

        campaign_paths = paths.campaign(self.campaign_name)
        gm_details_completed_dir = campaign_paths.queue("gm-details").completed
        gm_list_results_dir = campaign_paths.queue("gm-list").completed / "results"

        tasks_by_id: Dict[str, GmItemTask] = {}
        needs_gm_list_fallback: List[str] = []
        for place_id in place_ids:
            marker_path = gm_details_completed_dir / f"{place_id}.json"
            if not marker_path.exists():
                needs_gm_list_fallback.append(place_id)
                continue
            try:
                marker_task = GmItemTask.model_validate_json(marker_path.read_text())
            except (ValidationError, OSError) as e:
                logger.warning(
                    "Could not parse completed marker for %s: %s - falling back to gm-list.",
                    place_id, e,
                )
                needs_gm_list_fallback.append(place_id)
                continue
            # Fresh task, not the marker verbatim: resets attempts to 0 and
            # drops the (already-excluded, but be explicit) transient
            # ack_token - this is a new attempt, not a continuation.
            #
            # force_refresh is deliberately NOT carried over from the marker
            # (2026-08-15 incident: propagating it here pushed 283 enrichment
            # tasks with force_refresh=true, threatening to overwrite good
            # website.md content - keyed by company_slug, not place_id - for
            # a re-scrape that only exists to fill a WAL gap, not to force a
            # refresh). This tool recovers a lost result; it must not also
            # opt records into a disruptive full re-enrichment as a side
            # effect.
            tasks_by_id[place_id] = GmItemTask(
                place_id=place_id,
                campaign_name=self.campaign_name,
                name=marker_task.name,
                company_slug=marker_task.company_slug,
                gmb_url=marker_task.gmb_url,
                category=marker_task.category,
                discovery_phrase=marker_task.discovery_phrase,
                discovery_tile_id=marker_task.discovery_tile_id,
            )

        if needs_gm_list_fallback:
            rows_by_id = find_gm_list_rows(gm_list_results_dir, set(needs_gm_list_fallback))
            for place_id in needs_gm_list_fallback:
                row = rows_by_id.get(place_id)
                if row is None:
                    continue
                tasks_by_id[place_id] = GmItemTask(
                    place_id=place_id,
                    campaign_name=self.campaign_name,
                    name=row.get("name", ""),
                    company_slug=row.get("company_slug", ""),
                    gmb_url=row.get("gmb_url") or None,
                    category=row.get("category") or None,
                    discovery_phrase=row.get("discovery_phrase") or None,
                    discovery_tile_id=row.get("discovery_tile_id") or None,
                )

        try:
            nodes = ClusterService(self.campaign_name).get_nodes()
        except Exception as e:
            logger.warning("Could not resolve cluster nodes for %s: %s", self.campaign_name, e)
            nodes = []
        candidate_nodes = [n for n in nodes if n.enabled] or nodes

        out_rows: List[RequeueRow] = []
        for place_id in place_ids:
            task = tasks_by_id.get(place_id)
            if task is None:
                out_rows.append(
                    RequeueRow(
                        place_id=place_id,
                        status="not_found",
                        detail="no completed marker or gm-list result to build a task from",
                    )
                )
                continue

            if not candidate_nodes:
                out_rows.append(
                    RequeueRow(place_id=place_id, status="ssh_error", detail="no cluster nodes")
                )
                continue

            payload = json.dumps(task.model_dump())
            shard = get_place_id_shard(place_id)
            remote_base = f"repos/data/campaigns/{self.campaign_name}/queues/gm-details"

            push_node = candidate_nodes[0]
            push_target = push_node.ip_address or push_node.hostname
            remote_pending_dir = shlex.quote(f"{remote_base}/pending/{shard}/{place_id}")
            try:
                write_result = subprocess.run(
                    [
                        "ssh", "-o", "ConnectTimeout=10", f"mstouffer@{push_target}",
                        f"mkdir -p {remote_pending_dir} && cat > {remote_pending_dir}/task.json",
                    ],
                    input=payload, capture_output=True, text=True, timeout=20,
                )
            except subprocess.TimeoutExpired:
                out_rows.append(
                    RequeueRow(
                        place_id=place_id, status="ssh_error",
                        detail=f"{push_node.hostname}: timeout writing pending task",
                    )
                )
                continue

            if write_result.returncode != 0:
                out_rows.append(
                    RequeueRow(
                        place_id=place_id, status="ssh_error",
                        detail=f"{push_node.hostname}: {write_result.stderr.strip()}",
                    )
                )
                continue

            # Pending task is confirmed written - now safe to clear the
            # stale completed marker, checking every node since it could
            # have been produced by any of them.
            rm_errors: List[str] = []
            for node in nodes:
                node_target = node.ip_address or node.hostname
                remote_completed = shlex.quote(f"{remote_base}/completed/{place_id}.json")
                try:
                    rm_result = subprocess.run(
                        [
                            "ssh", "-o", "ConnectTimeout=10", f"mstouffer@{node_target}",
                            f"rm -f {remote_completed}",
                        ],
                        capture_output=True, text=True, timeout=20,
                    )
                    if rm_result.returncode != 0:
                        rm_errors.append(f"{node.hostname}: {rm_result.stderr.strip()}")
                except subprocess.TimeoutExpired:
                    rm_errors.append(f"{node.hostname}: timeout")

            detail = f"pushed to {push_node.hostname}"
            if rm_errors:
                detail += (
                    "; WARNING: could not clear stale completed marker on: "
                    + "; ".join(rm_errors)
                )
            out_rows.append(RequeueRow(place_id=place_id, status="requeued", detail=detail))

        return RequeueResult(campaign_name=self.campaign_name, index_name=index_name, rows=out_rows)

    # ------------------------------------------------------------------
    # Requeue (recover the "Identity Gap (enrichment-enqueue)" gap
    # cocli audit campaign finds: checkpoint + resolved domain, but never
    # enqueued into the enrichment queue at all)
    # ------------------------------------------------------------------

    def requeue_enrichment_gaps(self, place_ids: List[str]) -> RequeueResult:
        """Push a fresh EnrichmentTask for each place_id whose prospect
        record has a resolved domain but was never enqueued for enrichment -
        the "Identity Gap (enrichment-enqueue)" category from
        cocli audit campaign / docs/_schema/traceability.md.

        Confirmed live 2026-08-18 against turboship: 1,667 such records
        (1,600 current-format place_ids, 67 legacy-format).

        Writes directly to a Pi node's filesystem over SSH, not locally -
        same reason as requeue_stuck_details: pending/ is never synced in
        either direction, only completed/ is, so a local
        FilesystemQueue.push() would write to a directory no worker polls.

        Batched into ONE SSH call per target node (not one call per
        record) - unlike requeue_stuck_details, which is built for a
        handful of manually-identified stragglers, this is meant to run
        against results from a whole-campaign audit that can easily be
        four figures, where a per-record SSH round trip would be the
        dominant cost.

        Re-checks each domain's current enrichment status right before
        pushing (not just trusting a possibly-stale audit CSV) and skips
        anything that already has a completed/pending/failed record -
        idempotent against being run again, or against genuine progress
        made between the audit run and this call.
        """
        import shlex
        import subprocess

        from cocli.core.prospect_trace import ProspectDomainIndex, QueueBucketCheck
        from cocli.core.prospects_csv_manager import ProspectsIndexManager
        from cocli.core.sharding import get_domain_shard
        from cocli.models.campaigns.queues.enrichment import EnrichmentTask
        from cocli.services.cluster_service import ClusterService

        campaign_paths = paths.campaign(self.campaign_name)
        checkpoint_path = ProspectsIndexManager(self.campaign_name).checkpoint_path
        wal_root = paths.campaign(self.campaign_name).index("google_maps_prospects").wal
        enrichment_queue = campaign_paths.queue("enrichment")

        domain_index = ProspectDomainIndex(checkpoint_path, wal_root)
        enrichment_check = QueueBucketCheck(
            "enrichment",
            enrichment_queue.completed,
            enrichment_queue.pending,
            enrichment_queue.path / "failed",
        )

        out_rows: List[RequeueRow] = []
        tasks_to_push: List[EnrichmentTask] = []
        seen_domains: set[str] = set()
        for place_id in place_ids:
            domain = domain_index.get_domain(place_id)
            if not domain:
                out_rows.append(
                    RequeueRow(place_id=place_id, status="not_found", detail="no domain resolved")
                )
                continue

            current = enrichment_check.check(domain)
            if current.state != "never seen":
                out_rows.append(
                    RequeueRow(
                        place_id=place_id, status="skipped",
                        detail=f"domain {domain} already {current.state} - not re-pushing",
                    )
                )
                continue

            if domain in seen_domains:
                out_rows.append(
                    RequeueRow(
                        place_id=place_id, status="skipped",
                        detail=f"domain {domain} already queued this run (shared by another place_id)",
                    )
                )
                continue

            slug = domain_index.get_slug(place_id) or domain
            tasks_to_push.append(
                EnrichmentTask(
                    domain=domain,
                    company_slug=slug,
                    campaign_name=self.campaign_name,
                    force_refresh=False,
                )
            )
            seen_domains.add(domain)
            out_rows.append(RequeueRow(place_id=place_id, status="requeued", detail=f"domain {domain}"))

        if not tasks_to_push:
            return RequeueResult(
                campaign_name=self.campaign_name, index_name="enrichment", rows=out_rows
            )

        try:
            nodes = ClusterService(self.campaign_name).get_nodes()
        except Exception as e:
            logger.warning("Could not resolve cluster nodes for %s: %s", self.campaign_name, e)
            nodes = []
        candidate_nodes = [n for n in nodes if n.enabled] or nodes
        if not candidate_nodes:
            for row in out_rows:
                if row.status == "requeued":
                    row.status = "ssh_error"
                    row.detail = "no cluster nodes"
            return RequeueResult(
                campaign_name=self.campaign_name, index_name="enrichment", rows=out_rows
            )

        push_node = candidate_nodes[0]
        push_target = push_node.ip_address or push_node.hostname
        remote_base = f"repos/data/campaigns/{self.campaign_name}/queues/enrichment/pending"

        # Per-record isolation, not a single set -e script: confirmed live
        # 2026-08-18 that some pending dirs are stale, root-owned leftovers
        # (created by the containerized worker, which runs as root, while
        # this SSH session runs as an unprivileged user) - mkdir/cat fails
        # with Permission Denied on those specific dirs. Under set -e, ONE
        # such record aborted the entire batch, discarding every write that
        # had already succeeded before it - only surfaced at real scale
        # (failed on records 79-request-in on a batch of 100; passed clean
        # on a batch of 20). Now: use `sudo` (confirmed passwordless on the
        # Pi nodes) so a stale root-owned dir doesn't block the write at
        # all, wrap each record in its own if/then/else so one failure
        # can't cascade, and print a per-domain OK/FAIL marker to parse
        # back out - the whole point of batching is throughput, but that
        # must not come at the cost of "any one record's mkdir stops here"
        # atomicity across totally unrelated records.
        script_lines = []
        for task in tasks_to_push:
            shard = get_domain_shard(task.domain)
            remote_dir = shlex.quote(f"{remote_base}/{shard}/{task.domain}")
            delimiter = f"COCLI_TASK_EOF_{shard}_{abs(hash(task.domain))}"
            marker = shlex.quote(task.domain)
            script_lines.append(
                f"if sudo mkdir -p {remote_dir} && "
                f"sudo tee {remote_dir}/task.json > /dev/null <<'{delimiter}'\n"
                f"{task.model_dump_json()}\n"
                f"{delimiter}\n"
                f"then echo COCLI_OK:{marker}; else echo COCLI_FAIL:{marker}; fi"
            )
        script = "\n".join(script_lines) + "\n"

        try:
            write_result = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=15", f"mstouffer@{push_target}", "bash -s"],
                input=script, capture_output=True, text=True, timeout=300,
            )
        except subprocess.TimeoutExpired:
            write_result = None

        if write_result is None:
            for row in out_rows:
                if row.status == "requeued":
                    row.status = "ssh_error"
                    row.detail = f"{push_node.hostname}: timeout"
        elif write_result.returncode != 0 and not write_result.stdout.strip():
            # A nonzero exit with no per-record markers means the SSH
            # connection/session itself failed, not an individual record -
            # e.g. auth failure, host unreachable.
            for row in out_rows:
                if row.status == "requeued":
                    row.status = "ssh_error"
                    row.detail = f"{push_node.hostname}: {write_result.stderr.strip()}"
        else:
            ok_domains = set()
            fail_domains = set()
            for line in write_result.stdout.splitlines():
                if line.startswith("COCLI_OK:"):
                    ok_domains.add(line[len("COCLI_OK:"):])
                elif line.startswith("COCLI_FAIL:"):
                    fail_domains.add(line[len("COCLI_FAIL:"):])

            for row in out_rows:
                if row.status != "requeued":
                    continue
                domain = row.detail.removeprefix("domain ")
                if domain in ok_domains:
                    row.detail += f" - pushed to {push_node.hostname}"
                elif domain in fail_domains:
                    row.status = "ssh_error"
                    row.detail = f"{push_node.hostname}: mkdir/write failed for {domain} (stale permissions?)"
                else:
                    row.status = "ssh_error"
                    row.detail = f"{push_node.hostname}: no result marker seen for {domain}"

        return RequeueResult(campaign_name=self.campaign_name, index_name="enrichment", rows=out_rows)

    # ------------------------------------------------------------------
    # Requeue gm-details for place_ids the checkpoint already knows (name,
    # slug, gmb_url) but that have no gm-details completed/pending record -
    # e.g. an older scrape cycle whose original gm-list source files have
    # since been cleaned up, so requeue_stuck_details' gm-list-result
    # fallback has nothing to read either.
    # ------------------------------------------------------------------

    def requeue_missing_details(
        self, place_ids: List[str], batch_size: int = 1000
    ) -> RequeueResult:
        """Push a fresh gm-details task for each place_id, built directly
        from the prospects checkpoint (name/company_slug/category/gmb_url) -
        no gm-list result file needed, unlike requeue_stuck_details.

        Confirmed live 2026-08-22 against turboship: ~11,000 checkpoint
        place_ids from an earlier scrape cycle have no gm-details
        completed/pending record and no matching file left in the current
        gm-list results directory either - their original gm-list source
        was already cleaned up by normal queue lifecycle, but the
        checkpoint retained their identity + gmb_url from whenever they
        were first compacted, which is enough to build a fresh gm-details
        task without re-running gm-list at all.

        Batched into one SSH call per chunk (batch_size place_ids at a
        time, not one call per record) with the same sudo + per-record
        if/then/else isolation as requeue_enrichment_gaps - this is meant
        to run against four-to-five-figure batches, where both a
        per-record SSH round trip and one giant unbounded script would be
        real risks at that scale.

        Only checks the local (synced) gm-details completed/ bucket to
        skip already-done place_ids - pending/ is never synced locally
        (see requeue_stuck_details), so a place_id already pending on the
        Pi may get pushed again here. Harmless: gm-details pending tasks
        are filename-keyed by place_id, so a repeat push just overwrites
        the existing pending task.json with equivalent content, not a
        duplicate.
        """
        import shlex
        import subprocess

        import duckdb

        from cocli.core.prospect_trace import QueueBucketCheck
        from cocli.core.prospects_csv_manager import ProspectsIndexManager
        from cocli.core.sharding import get_place_id_shard
        from cocli.models.campaigns.indexes.google_maps_prospect import (
            GoogleMapsProspect,
        )
        from cocli.models.campaigns.queues.gm_details import GmItemTask
        from cocli.services.cluster_service import ClusterService

        checkpoint_path = ProspectsIndexManager(self.campaign_name).checkpoint_path
        if not checkpoint_path.exists():
            return RequeueResult(
                campaign_name=self.campaign_name,
                index_name="google_maps_prospects",
                rows=[
                    RequeueRow(place_id=pid, status="not_found", detail="no checkpoint")
                    for pid in place_ids
                ],
            )

        model_fields = GoogleMapsProspect.model_fields
        columns: Dict[str, str] = {}
        for name, field in model_fields.items():
            field_type = "VARCHAR"
            type_str = str(field.annotation)
            if "int" in type_str:
                field_type = "INTEGER"
            elif "float" in type_str:
                field_type = "DOUBLE"
            columns[name] = field_type

        con = duckdb.connect(database=":memory:")
        con.execute(
            "CREATE TABLE prospects AS SELECT * FROM read_csv(?, delim=chr(31), "
            "header=False, columns=?, auto_detect=False, ignore_errors=True, quote='')",
            [str(checkpoint_path), columns],
        )
        placeholders = ", ".join("?" for _ in place_ids)
        rows_by_id = {
            r[0]: r
            for r in con.execute(
                "SELECT place_id, name, slug, category, gmb_url, "
                "discovery_phrase, discovery_tile_id FROM prospects "
                f"WHERE place_id IN ({placeholders})",
                place_ids,
            ).fetchall()
        }

        campaign_paths = paths.campaign(self.campaign_name)
        gm_details_queue = campaign_paths.queue("gm-details")
        completed_check = QueueBucketCheck(
            "gm-details", gm_details_queue.completed, gm_details_queue.pending
        )

        out_rows: List[RequeueRow] = []
        tasks_to_push: List[tuple[str, str]] = []  # (place_id, task_json)
        for place_id in place_ids:
            row = rows_by_id.get(place_id)
            gmb_url = row[4] if row else None
            if not row or not gmb_url or not gmb_url.strip():
                out_rows.append(
                    RequeueRow(
                        place_id=place_id, status="not_found",
                        detail="no checkpoint row with a gmb_url",
                    )
                )
                continue

            if completed_check.check(place_id).state == "completed":
                out_rows.append(
                    RequeueRow(place_id=place_id, status="skipped", detail="already completed")
                )
                continue

            task = GmItemTask(
                place_id=place_id,
                campaign_name=self.campaign_name,
                name=row[1] or "",
                company_slug=row[2] or "",
                gmb_url=gmb_url,
                category=row[3] or None,
                discovery_phrase=row[5] or None,
                discovery_tile_id=row[6] or None,
            )
            tasks_to_push.append((place_id, task.model_dump_json()))
            out_rows.append(RequeueRow(place_id=place_id, status="requeued", detail=""))

        if not tasks_to_push:
            return RequeueResult(
                campaign_name=self.campaign_name, index_name="google_maps_prospects", rows=out_rows
            )

        try:
            nodes = ClusterService(self.campaign_name).get_nodes()
        except Exception as e:
            logger.warning("Could not resolve cluster nodes for %s: %s", self.campaign_name, e)
            nodes = []
        candidate_nodes = [n for n in nodes if n.enabled] or nodes
        if not candidate_nodes:
            for out_row in out_rows:
                if out_row.status == "requeued":
                    out_row.status = "ssh_error"
                    out_row.detail = "no cluster nodes"
            return RequeueResult(
                campaign_name=self.campaign_name, index_name="google_maps_prospects", rows=out_rows
            )

        push_node = candidate_nodes[0]
        push_target = push_node.ip_address or push_node.hostname
        remote_base = f"repos/data/campaigns/{self.campaign_name}/queues/gm-details/pending"

        rows_by_place_id = {r.place_id: r for r in out_rows}
        for chunk_start in range(0, len(tasks_to_push), batch_size):
            chunk = tasks_to_push[chunk_start : chunk_start + batch_size]
            script_lines = []
            for place_id, task_json in chunk:
                shard = get_place_id_shard(place_id)
                remote_dir = shlex.quote(f"{remote_base}/{shard}/{place_id}")
                delimiter = f"COCLI_TASK_EOF_{shard}_{abs(hash(place_id))}"
                marker = shlex.quote(place_id)
                script_lines.append(
                    f"if sudo mkdir -p {remote_dir} && "
                    f"sudo tee {remote_dir}/task.json > /dev/null <<'{delimiter}'\n"
                    f"{task_json}\n"
                    f"{delimiter}\n"
                    f"then echo COCLI_OK:{marker}; else echo COCLI_FAIL:{marker}; fi"
                )
            script = "\n".join(script_lines) + "\n"

            try:
                write_result = subprocess.run(
                    ["ssh", "-o", "ConnectTimeout=15", f"mstouffer@{push_target}", "bash -s"],
                    input=script, capture_output=True, text=True, timeout=300,
                )
            except subprocess.TimeoutExpired:
                write_result = None

            chunk_ids = {pid for pid, _ in chunk}
            if write_result is None:
                for pid in chunk_ids:
                    rows_by_place_id[pid].status = "ssh_error"
                    rows_by_place_id[pid].detail = f"{push_node.hostname}: timeout"
            elif write_result.returncode != 0 and not write_result.stdout.strip():
                for pid in chunk_ids:
                    rows_by_place_id[pid].status = "ssh_error"
                    rows_by_place_id[pid].detail = f"{push_node.hostname}: {write_result.stderr.strip()}"
            else:
                ok_ids = set()
                fail_ids = set()
                for line in write_result.stdout.splitlines():
                    if line.startswith("COCLI_OK:"):
                        ok_ids.add(line[len("COCLI_OK:"):])
                    elif line.startswith("COCLI_FAIL:"):
                        fail_ids.add(line[len("COCLI_FAIL:"):])
                for pid in chunk_ids:
                    if pid in ok_ids:
                        rows_by_place_id[pid].detail = f"pushed to {push_node.hostname}"
                    elif pid in fail_ids:
                        rows_by_place_id[pid].status = "ssh_error"
                        rows_by_place_id[pid].detail = f"{push_node.hostname}: mkdir/write failed (stale permissions?)"
                    else:
                        rows_by_place_id[pid].status = "ssh_error"
                        rows_by_place_id[pid].detail = f"{push_node.hostname}: no result marker seen"

        return RequeueResult(
            campaign_name=self.campaign_name, index_name="google_maps_prospects", rows=out_rows
        )

    # ------------------------------------------------------------------
    # Purge checkpoint rows whose place_id can never validate (legacy
    # 0x-prefixed/colon-containing CID format) - not a missing-data
    # problem, a format problem with no correction queue wanted for it.
    # ------------------------------------------------------------------

    def purge_invalid_place_ids(
        self, index_name: str = "google_maps_prospects", dry_run: bool = True
    ) -> PurgeInvalidPlaceIdsResult:
        """Removes checkpoint rows whose place_id fails PlaceID validation
        (starts with "0x" or contains ":" - a legacy Google CID format,
        never a valid modern Place ID).

        These can never produce a savable GoogleMapsProspect - IDENTITY
        SHIELD in google_maps_details.py always rejects them at
        GoogleMapsProspect.from_raw(), even after a full, successful
        detail-page scrape (confirmed live 2026-08-22 against turboship:
        323 such rows, every one with a real gmb_url, every one scraping
        successfully in 40-60s before failing at the final identity
        check). Leaving them in the checkpoint means every future
        gap-audit/requeue tool rediscovers and re-wastes the same worker
        time on them indefinitely - discarding them here is a deliberate
        choice (Mark, 2026-08-22) over building a place_id-correction
        queue for what should be a rare case.

        Backs up the checkpoint before rewriting (matches every other
        checkpoint-touching tool in this module), then re-uploads the
        corrected checkpoint to S3 via CompactManager.commit_remote() -
        the same mechanism a normal compact uses - so the stale,
        still-containing version can't get pulled back down by another
        machine and undo this.

        Does not touch the gm-details pending queue on any Pi node -
        pending/ never syncs locally (see requeue_stuck_details), so that
        cleanup has to happen separately, over SSH, against the actual
        node(s).
        """
        from cocli.core.compact import CompactManager
        from cocli.core.prospects_csv_manager import ProspectsIndexManager
        from cocli.models.place_id import validate_place_id
        from cocli.utils.backup_utils import timestamped_backup_path

        checkpoint_path = ProspectsIndexManager(self.campaign_name).checkpoint_path
        if not checkpoint_path.exists():
            return PurgeInvalidPlaceIdsResult(
                campaign_name=self.campaign_name, index_name=index_name, dry_run=dry_run
            )

        US = "\x1f"
        lines = checkpoint_path.read_text(encoding="utf-8").splitlines()

        kept_lines: List[str] = []
        removed_ids: List[str] = []
        for line in lines:
            if not line:
                continue
            place_id = line.split(US, 1)[0]
            try:
                validate_place_id(place_id)
            except ValueError:
                removed_ids.append(place_id)
                continue
            kept_lines.append(line)

        result = PurgeInvalidPlaceIdsResult(
            campaign_name=self.campaign_name,
            index_name=index_name,
            dry_run=dry_run,
            removed_place_ids=removed_ids,
            checkpoint_before=len(lines),
            checkpoint_after=len(kept_lines),
        )
        if dry_run or not removed_ids:
            return result

        backup_path = timestamped_backup_path(checkpoint_path)
        checkpoint_path.rename(backup_path)
        checkpoint_path.write_text(
            "".join(line + "\n" for line in kept_lines), encoding="utf-8"
        )

        manager = CompactManager(campaign_name=self.campaign_name, index_name=index_name)
        manager.commit_remote()

        return result

    # ------------------------------------------------------------------
    # Archive WAL records that don't match the current full schema
    # ------------------------------------------------------------------

    def archive_incomplete_schema_wal(
        self,
        index_name: str = "google_maps_prospects",
        required_field_count: int = 57,
        dry_run: bool = True,
    ) -> ArchiveWalResult:
        """Move WAL records with fewer than required_field_count fields out
        of the active WAL into archive_wal/, so a compaction only ever folds
        in records matching the current schema.

        Confirmed live 2026-08-18 against roadmap's real WAL (31,821
        records): row field-count directly tracks schema era, and it's not
        just older records being *shorter* - the 55-field (oldest) era has
        a genuinely different tail field ORDER, not merely fewer trailing
        fields (unlike the 56-field era, which is a clean append-diff of
        the current 57-field schema minus the newest field). Reading a
        55-field record with the current schema's fixed positional field
        names would silently misassign discovery_phrase/discovery_tile_id/
        email/etc. Rather than special-case "safe short" vs "unsafe
        reordered" rows, archive anything short of the full current schema
        uniformly - it's all equally not eligible to fold into a checkpoint
        that's supposed to reflect the current schema, regardless of which
        specific way it's incomplete.

        Before moving anything, extracts place_id/slug/name (the minimal
        GoogleMapsIdx-shaped identity fields - see
        cocli/models/campaigns/indexes/google_maps_idx.py, deliberately not
        materialized as its own stored index yet) into a single
        archived_place_idx.usv sidecar, append-only, so nothing is lost:
        once a real google_maps_idx lookup gets built, these can seed it
        without re-deriving them from the archived files.

        Runs on every enabled node for this campaign (not just one, unlike
        the enrichment-gap push) - this is a per-node local read+move over
        each node's own WAL, no cross-node race to worry about. Uses `sudo`
        (confirmed passwordless on the Pi nodes) since WAL file ownership
        is mixed - some root (written by the containerized worker), some
        the SSH user (written by earlier code/manual operations).
        """
        import re
        import subprocess

        from cocli.services.cluster_service import ClusterService

        try:
            nodes = ClusterService(self.campaign_name).get_nodes()
        except Exception as e:
            logger.warning("Could not resolve cluster nodes for %s: %s", self.campaign_name, e)
            nodes = []
        candidate_nodes = [n for n in nodes if n.enabled] or nodes

        remote_script = f"""
import re
import shutil
from pathlib import Path

US = chr(0x1f)
campaign = {self.campaign_name!r}
index_name = {index_name!r}
required = {required_field_count!r}
dry_run = {dry_run!r}

wal = Path(f"/home/mstouffer/repos/data/campaigns/{{campaign}}/indexes/{{index_name}}/wal")
archive_root = Path(f"/home/mstouffer/repos/data/campaigns/{{campaign}}/indexes/{{index_name}}/archive_wal")
idx_extract_path = Path(f"/home/mstouffer/repos/data/campaigns/{{campaign}}/indexes/{{index_name}}/archived_place_idx.usv")

archived = 0
kept = 0
idx_lines = []

if wal.exists():
    for f in wal.rglob("*.usv"):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fields = text.rstrip(chr(10)).split(US)
        if len(fields) >= required:
            kept += 1
            continue
        place_id = fields[0] if len(fields) > 0 else ""
        slug = fields[1] if len(fields) > 1 else ""
        name = fields[2] if len(fields) > 2 else ""
        idx_lines.append(US.join([place_id, slug, name]))
        archived += 1
        if not dry_run:
            rel = f.relative_to(wal)
            dest = archive_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(f), str(dest))

if idx_lines and not dry_run:
    idx_extract_path.parent.mkdir(parents=True, exist_ok=True)
    with open(idx_extract_path, "a", encoding="utf-8") as out:
        for line in idx_lines:
            out.write(line + chr(10))

print(f"COCLI_ARCHIVE_RESULT archived={{archived}} kept={{kept}}")
"""

        node_results: List[ArchiveWalNodeResult] = []
        for node in candidate_nodes:
            target = node.ip_address or node.hostname
            try:
                result = subprocess.run(
                    ["ssh", "-o", "ConnectTimeout=15", f"mstouffer@{target}", "sudo -n python3 -"],
                    input=remote_script, capture_output=True, text=True, timeout=180,
                )
            except subprocess.TimeoutExpired:
                node_results.append(ArchiveWalNodeResult(hostname=node.hostname, error="timeout"))
                continue

            match = re.search(r"COCLI_ARCHIVE_RESULT archived=(\d+) kept=(\d+)", result.stdout)
            if not match:
                node_results.append(
                    ArchiveWalNodeResult(
                        hostname=node.hostname,
                        error=result.stderr.strip() or "no result line seen",
                    )
                )
                continue

            node_results.append(
                ArchiveWalNodeResult(
                    hostname=node.hostname,
                    archived=int(match.group(1)),
                    kept=int(match.group(2)),
                )
            )

        return ArchiveWalResult(
            campaign_name=self.campaign_name,
            index_name=index_name,
            required_field_count=required_field_count,
            dry_run=dry_run,
            nodes=node_results,
        )

    # ------------------------------------------------------------------
    # Domain backfill
    # ------------------------------------------------------------------

    def backfill_domains(
        self,
        limit: int = 0,
        compact: bool = True,
        log_callback: Optional[LogCallback] = None,
    ) -> DomainBackfillResult:
        """Backfill the domain index from local website enrichment files."""
        from cocli.core.config import load_campaign_config
        from cocli.core.domain_index_manager import DomainIndexManager
        from cocli.models.campaigns.campaign import Campaign as CampaignModel

        camp_obj = CampaignModel.load(self.campaign_name)
        config = load_campaign_config(self.campaign_name)
        tag = config.get("campaign", {}).get("tag") or self.campaign_name

        manager = DomainIndexManager(camp_obj)
        _emit(log_callback, f"Scanning companies for tag '{tag}'...")
        added = manager.backfill_from_companies(tag, limit=limit)
        _emit(log_callback, f"Scanned and added {added} records to inbox.")
        did_compact = False
        if compact and added > 0:
            _emit(log_callback, "Compacting inbox into shards...")
            manager.compact_inbox()
            did_compact = True
            _emit(log_callback, "Compaction complete.")

        return DomainBackfillResult(
            campaign_name=self.campaign_name,
            tag=str(tag),
            records_added=added,
            compacted=did_compact,
            message=f"Backfill finished: {added} records added"
            + (" and compacted." if did_compact else "."),
        )

    # ------------------------------------------------------------------
    # Datapackage
    # ------------------------------------------------------------------

    @staticmethod
    def index_model_map() -> Dict[str, Type[BaseUsvModel]]:
        """Map index names to their Frictionless/Pydantic USV models."""
        from cocli.models.campaigns.indexes.domains import WebsiteDomainCsv
        from cocli.models.campaigns.indexes.email import EmailEntry
        from cocli.models.campaigns.indexes.google_maps_prospect import (
            GoogleMapsProspect,
        )

        return {
            "domains": WebsiteDomainCsv,
            "google_maps_prospects": GoogleMapsProspect,
            "emails": EmailEntry,
        }

    def resolve_index_dir(
        self, index_name: str, campaign: Optional[str] = None
    ) -> Path:
        """Resolve the on-disk directory for an index station."""
        campaign_name = campaign or self.campaign_name
        if index_name == "domains":
            return paths.root / "indexes" / "domains"
        if not campaign_name:
            raise ValueError(f"Campaign required for index: {index_name}")
        return paths.campaign(campaign_name).index(index_name).path

    def write_datapackage(
        self,
        index_name: str,
        force: bool = False,
        campaign: Optional[str] = None,
    ) -> WriteDatapackageResult:
        """
        Write Frictionless datapackage.json for an index from its Pydantic model.

        Raises:
            ValueError: unknown index name, or campaign required but missing
            SchemaConflictError: breaking schema drift without --force
        """
        model_map = self.index_model_map()
        model_class = model_map.get(index_name)
        if model_class is None:
            raise ValueError(f"Unknown index type: {index_name}")

        target_dir = self.resolve_index_dir(index_name, campaign=campaign)
        if not target_dir.exists():
            logger.info("Creating index directory %s", target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)

        resource_name = index_name.replace("_", "-")
        resource_path = "*.usv"
        from ..core.ordinant import IndexIdentity
        if index_name == IndexIdentity.PROSPECTS:
            c_name = campaign or self.campaign_name
            resource_path = paths.campaign(c_name).index(IndexIdentity.PROSPECTS).checkpoint_filename



        model_class.save_datapackage(
            target_dir, resource_name, resource_path, force=force
        )
        return WriteDatapackageResult(
            index_name=index_name,
            target_dir=target_dir,
            resource_name=resource_name,
            resource_path=resource_path,
            message=f"Successfully wrote datapackage.json to {target_dir}",
        )


def setup_index_log_file(campaign_name: str, index_name: str) -> Path:
    """Create a timestamped compact log path under .logs/ (CLI concern helper)."""
    logs_dir = Path(".logs")
    logs_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return logs_dir / f"compact_{campaign_name}_{index_name}_{timestamp}.log"


# Re-export for command-layer exception handling
__all__ = [
    "IndexService",
    "IndexStatusReport",
    "IndexLockStatus",
    "IndexCheckpointStatus",
    "CompactResult",
    "DomainBackfillResult",
    "WriteDatapackageResult",
    "setup_index_log_file",
    "SchemaConflictError",
]
