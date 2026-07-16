"""Index orchestration services for compaction, status, domain backfill, and datapackages.

Domain/orchestration layer (product-specific). No Rich/console presentation —
callers format Intermediate artifacts (status reports, compact results) for CLI/TUI.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Type

from pydantic import BaseModel, Field

from cocli.core.paths import paths
from cocli.models.base import BaseUsvModel, SchemaConflictError

logger = logging.getLogger(__name__)


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
        checkpoint_key = manager.s3_index_prefix + "prospects.checkpoint.usv"
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
    ) -> CompactResult:
        """
        Compact WAL into the main checkpoint (Freeze-Ingest-Merge-Commit).

        Self-heals interrupted runs first, then runs a full compact cycle under lock.
        """
        from cocli.core.compact import CompactManager

        recovered = self.list_interrupted_runs(index_name)
        for run_id in recovered:
            self.recover_interrupted_run(index_name, run_id, log_file=log_file)

        manager = CompactManager(
            campaign_name=self.campaign_name,
            index_name=index_name,
            log_file=log_file,
        )

        if not manager.acquire_lock():
            return CompactResult(
                campaign_name=self.campaign_name,
                index_name=index_name,
                success=False,
                recovered_runs=recovered,
                message="Lock acquisition failed (another compact may be running).",
                log_file=log_file,
            )

        try:
            moved = manager.isolate_wal()
            if moved == 0:
                return CompactResult(
                    campaign_name=self.campaign_name,
                    index_name=index_name,
                    success=True,
                    recovered_runs=recovered,
                    isolated_files=0,
                    message="Nothing to compact.",
                    log_file=log_file,
                )

            manager.acquire_staging()
            manager.merge()
            manager.commit_remote()
            manager.cleanup()

            return CompactResult(
                campaign_name=self.campaign_name,
                index_name=index_name,
                success=True,
                recovered_runs=recovered,
                isolated_files=moved,
                message="Compaction workflow finished successfully.",
                log_file=log_file,
            )
        except Exception as e:
            logger.error("Compaction failed: %s", e, exc_info=True)
            return CompactResult(
                campaign_name=self.campaign_name,
                index_name=index_name,
                success=False,
                recovered_runs=recovered,
                message=f"Compaction failed: {e}",
                log_file=log_file,
            )
        finally:
            manager.release_lock()

    # ------------------------------------------------------------------
    # Domain backfill
    # ------------------------------------------------------------------

    def backfill_domains(
        self,
        limit: int = 0,
        compact: bool = True,
    ) -> DomainBackfillResult:
        """Backfill the domain index from local website enrichment files."""
        from cocli.core.config import load_campaign_config
        from cocli.core.domain_index_manager import DomainIndexManager
        from cocli.models.campaigns.campaign import Campaign as CampaignModel

        camp_obj = CampaignModel.load(self.campaign_name)
        config = load_campaign_config(self.campaign_name)
        tag = config.get("campaign", {}).get("tag") or self.campaign_name

        manager = DomainIndexManager(camp_obj)
        added = manager.backfill_from_companies(tag, limit=limit)
        did_compact = False
        if compact and added > 0:
            manager.compact_inbox()
            did_compact = True

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
            KeyError: unknown index name
            ValueError: campaign required but missing
            SchemaConflictError: breaking schema drift without --force
        """
        model_map = self.index_model_map()
        model_class = model_map.get(index_name)
        if model_class is None:
            raise KeyError(f"Unknown index type: {index_name}")

        target_dir = self.resolve_index_dir(index_name, campaign=campaign)
        if not target_dir.exists():
            logger.info("Creating index directory %s", target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)

        resource_name = index_name.replace("_", "-")
        resource_path = "*.usv"
        if index_name == "google_maps_prospects":
            resource_path = "prospects.checkpoint.usv"

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
