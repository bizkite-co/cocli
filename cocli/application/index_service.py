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
    verdict: str


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

    def trace_prospects(
        self, place_ids: List[str], index_name: str = "google_maps_prospects"
    ) -> ProspectTraceResult:
        """Trace each place_id across gm-list -> gm-details -> Pi WAL ->
        checkpoint, reporting where (if anywhere) its trail goes cold.

        Built from the ad hoc investigation of a 2026-08-13 incident where a
        fresh compaction dropped previously-qualifying prospects. See
        cocli/core/prospect_trace.py for the reusable station-check
        mechanism this is assembled from, and its docstring for why this
        exists alongside (not instead of) stations' own `stations inspect`.
        """
        from cocli.core.prospect_trace import (
            CheckpointPresenceCheck,
            GmListResultsCheck,
            PrebuiltSetCheck,
            QueueBucketCheck,
            StationCheck,
            diagnose_prospect_trace,
            trace_identities,
        )
        from cocli.core.prospects_csv_manager import ProspectsIndexManager

        campaign_paths = paths.campaign(self.campaign_name)
        gm_list_results_dir = campaign_paths.queue("gm-list").completed / "results"
        gm_details_queue = campaign_paths.queue("gm-details")
        checkpoint_path = ProspectsIndexManager(self.campaign_name).checkpoint_path

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

        rows: List[ProspectTraceRow] = []
        for trace_row in trace_identities(checks, place_ids):
            r = trace_row.results
            gm_list_result = r["gm-list"]
            gm_list_display = (
                f"{gm_list_result.state} ({gm_list_result.detail})"
                if gm_list_result.detail
                else gm_list_result.state
            )
            rows.append(
                ProspectTraceRow(
                    place_id=trace_row.identity,
                    gm_list=gm_list_display,
                    gm_details=r["gm-details"].state,
                    pi_wal=r["pi-wal"].state,
                    checkpoint=r["checkpoint"].state,
                    verdict=diagnose_prospect_trace(r),
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
        _run_details_task_loop): reconstruct a fresh task from the original
        gm-list result row and push it back onto the queue for a retry.

        Must write directly to a Pi node's filesystem over SSH, not locally:
        PiSyncService._SYNC_QUEUES only syncs gm-details/completed/ from Pi
        to this machine - pending/ is never synced in either direction. A
        local FilesystemGmDetailsQueue.push() would write to a pending/
        directory no worker ever polls, and the stale
        completed/{place_id}.json marker (which would otherwise make
        `trace` keep reporting "completed" forever) only exists on the Pi.

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

        from cocli.core.prospect_trace import find_gm_list_rows
        from cocli.core.sharding import get_place_id_shard
        from cocli.models.campaigns.queues.gm_details import GmItemTask
        from cocli.services.cluster_service import ClusterService

        campaign_paths = paths.campaign(self.campaign_name)
        gm_list_results_dir = campaign_paths.queue("gm-list").completed / "results"
        rows_by_id = find_gm_list_rows(gm_list_results_dir, set(place_ids))

        try:
            nodes = ClusterService(self.campaign_name).get_nodes()
        except Exception as e:
            logger.warning("Could not resolve cluster nodes for %s: %s", self.campaign_name, e)
            nodes = []
        candidate_nodes = [n for n in nodes if n.enabled] or nodes

        out_rows: List[RequeueRow] = []
        for place_id in place_ids:
            row = rows_by_id.get(place_id)
            if row is None:
                out_rows.append(
                    RequeueRow(
                        place_id=place_id,
                        status="not_found",
                        detail="no gm-list result to reconstruct a task from",
                    )
                )
                continue

            if not candidate_nodes:
                out_rows.append(
                    RequeueRow(place_id=place_id, status="ssh_error", detail="no cluster nodes")
                )
                continue

            task = GmItemTask(
                place_id=place_id,
                campaign_name=self.campaign_name,
                name=row.get("name", ""),
                company_slug=row.get("company_slug", ""),
                gmb_url=row.get("gmb_url") or None,
                category=row.get("category") or None,
                discovery_phrase=row.get("discovery_phrase") or None,
                discovery_tile_id=row.get("discovery_tile_id") or None,
            )
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
