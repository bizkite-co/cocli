import os
import json
import logging
import time
import subprocess
from pathlib import Path
from datetime import datetime, UTC
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError

from .config import get_campaign_dir

logger = logging.getLogger(__name__)

class CompactManager:
    """
    Implements the Freeze-Ingest-Merge-Commit (FIMC) pattern for sharded indexes.
    Uses S3-Native isolation to prevent race conditions with workers.
    """
    
    def __init__(self, campaign_name: str, index_name: str = "google_maps_prospects", log_file: Optional[Path] = None):
        self.campaign_name = campaign_name
        self.index_name = index_name
        self.run_id = f"run_{int(time.time())}"
        self.log_file = log_file
        
        # Local Paths derived via paths single-source-of-truth
        from .paths import paths
        self.index_paths = paths.campaign(campaign_name).index(index_name)
        self.data_root = paths.campaign(campaign_name).path
        self.index_dir = self.index_paths.path
        self.checkpoint_path = self.index_paths.checkpoint
        self.checkpoint_filename = self.index_paths.checkpoint_filename

        self.local_proc_dir = self.index_dir / "processing" / self.run_id
        
        # S3 Paths
        self.s3_index_prefix = f"campaigns/{campaign_name}/indexes/{index_name}/"
        self.s3_checkpoint_key = self.s3_index_prefix + self.checkpoint_filename
        self.s3_wal_prefix = self.s3_index_prefix + "wal/"
        self.s3_proc_prefix = self.s3_index_prefix + f"processing/{self.run_id}/"
        self.s3_lock_key = self.s3_index_prefix + "compact.lock"

        
        # S3 Client
        self._s3: Any = None
        self._bucket = self._load_bucket_name()

    def _load_bucket_name(self) -> str:
        """Loads bucket name from campaign config.toml"""
        import tomllib
        camp_dir = get_campaign_dir(self.campaign_name)
        if camp_dir:
            config_path = camp_dir / "config.toml"
            if config_path.exists():
                with open(config_path, "rb") as f:
                    data = tomllib.load(f)
                    bucket = data.get("aws", {}).get("data_bucket_name") or data.get("data_bucket_name")
                    if bucket:
                        return str(bucket)
        return ""

    @property
    def s3(self) -> Any:
        if self._s3 is None:
            self._s3 = boto3.client("s3")
        return self._s3

    def acquire_lock(self) -> bool:
        """Creates an atomic lock on S3 using If-None-Match."""
        logger.info(f"Attempting to acquire compaction lock: {self.s3_lock_key}")
        lock_data = {
            "run_id": self.run_id,
            "created_at": datetime.now(UTC).isoformat(),
            "host": os.uname().nodename
        }
        try:
            self.s3.put_object(
                Bucket=self._bucket,
                Key=self.s3_lock_key,
                Body=json.dumps(lock_data),
                IfNoneMatch='*'
            )
            logger.info("Lock acquired successfully.")
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == 'PreconditionFailed':
                logger.warning("Compaction lock already exists. Another process is running.")
            else:
                logger.error(f"Failed to acquire lock: {e}")
            return False

    def release_lock(self) -> None:
        """Removes the compaction lock from S3."""
        try:
            self.s3.delete_object(Bucket=self._bucket, Key=self.s3_lock_key)
            logger.info("Lock released.")
        except Exception as e:
            logger.error(f"Failed to release lock: {e}")

    def isolate_wal(self) -> int:
        """Moves files from wal/ AND out-of-place files in the root to processing/run_id/ on S3."""
        logger.info(f"Isolating WAL files to {self.s3_proc_prefix}...")
        
        # 1. MOVE REMOTE WAL -> PROCESSING
        src_wal = f"s3://{self._bucket}/{self.s3_wal_prefix}"
        dest = f"s3://{self._bucket}/{self.s3_proc_prefix}"
        
        try:
            from contextlib import nullcontext
            with open(self.log_file, "a") if self.log_file else nullcontext() as f:
                # Move everything from wal/ prefix
                subprocess.run(
                    ["aws", "s3", "mv", src_wal, dest, "--recursive", "--quiet"],
                    stdout=f, stderr=f, text=True
                )
                
                # 2. SWEEP: Move any USV/CSV files in the root that aren't the checkpoint
                # We use a single batch move with filters for high performance
                root_s3 = f"s3://{self._bucket}/{self.s3_index_prefix}"
                subprocess.run(
                    [
                        "aws", "s3", "mv", root_s3, dest,
                        "--recursive",
                        "--exclude", "*",
                        "--include", "*.usv",
                        "--include", "*.csv",
                        "--exclude", self.checkpoint_filename,
                        "--exclude", "validation_errors.usv",
                        "--exclude", "_*",
                        "--quiet"
                    ],
                    stdout=f, stderr=f, text=True
                )

            logger.info("Isolation complete.")
            
            # 2. PURGE LOCAL WAL AND ROOT NAKED FILES
            local_wal = self.index_dir / "wal"
            if local_wal.exists():
                logger.info(f"Purging local WAL shards from {local_wal}...")
                import shutil
                shutil.rmtree(local_wal)
                local_wal.mkdir(parents=True, exist_ok=True)
            
            # Purge local naked files in index root
            for f_path in self.index_dir.glob("*.usv"):
                if f_path.name != self.checkpoint_filename and f_path.name != "validation_errors.usv":
                    f_path.unlink()

            for f_path in self.index_dir.glob("*.csv"):
                f_path.unlink()
            
            return 1 
        except Exception as e:
            logger.error(f"Failed to isolate WAL: {e}")
            return 0

    def acquire_staging(self) -> None:
        """Syncs the processing/run_id/ folder from S3 to local disk using AWS CLI."""
        logger.info(f"Acquiring staging data to {self.local_proc_dir}...")
        self.local_proc_dir.mkdir(parents=True, exist_ok=True)
        
        src = f"s3://{self._bucket}/{self.s3_proc_prefix}"
        try:
            from contextlib import nullcontext
            with open(self.log_file, "a") if self.log_file else nullcontext() as f:
                subprocess.run(
                    ["aws", "s3", "sync", src, str(self.local_proc_dir), "--quiet"],
                    stdout=f, stderr=f, check=True
                )
            logger.info("Staging data acquired.")
        except Exception as e:
            logger.error(f"Failed to sync staging data: {e}")

    def _write_schema_sidecar_first(self) -> None:
        """Enforces Frictionless Data policy by writing datapackage.json sidecar BEFORE data writes."""
        try:
            if self.index_name == "google_maps_prospects":
                from ..models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
                GoogleMapsProspect.write_datapackage(self.campaign_name, output_dir=self.index_dir)
                logger.info(f"Sidecar datapackage.json written first for {self.index_name}")
        except Exception as e:
            logger.warning(f"Schema sidecar write failed for {self.index_name}: {e}")

    def merge(self) -> None:
        """Fold local WAL/staging into prospects.usv via stations commit path.

        DuckDB performs the scale LWW fold; stations PathBackend CAS-commits
        CURRENT and protect_path hardens ratified artifacts. S3 isolate/stage
        still feed ``local_proc_dir`` before this runs.
        """
        self._write_schema_sidecar_first()

        from cocli.core.stations_runtime import compact_prospects_local

        staging: list[Path] = []
        if self.local_proc_dir.exists():
            staging.append(self.local_proc_dir)

        ok = compact_prospects_local(
            self.index_dir,
            checkpoint_path=self.checkpoint_path,
            staging_dirs=staging or None,
            compactor_id=self.run_id,
        )
        if ok:
            logger.info(
                "Prospects merge via stations commit path → %s",
                self.checkpoint_path,
            )
            return

        # Fallback: empty staging/WAL — nothing to fold (legacy no-op)
        logger.info("No local prospect sources to merge via stations.")


        
    def commit_remote(self) -> None:
        """Uploads the new checkpoint to S3."""
        logger.info("Uploading updated checkpoint to S3...")
        self.s3.upload_file(str(self.checkpoint_path), self._bucket, self.s3_checkpoint_key)
        logger.info(f"S3 Checkpoint updated at {self.s3_checkpoint_key}.")


    def cleanup(self) -> None:
        """Purges staging data from local and remote."""
        logger.info("Cleaning up staging layers...")
        
        # Remote Cleanup using AWS CLI
        src = f"s3://{self._bucket}/{self.s3_proc_prefix}"
        try:
            from contextlib import nullcontext
            with open(self.log_file, "a") if self.log_file else nullcontext() as f:
                subprocess.run(["aws", "s3", "rm", src, "--recursive", "--quiet"], stdout=f, stderr=f, check=True)
        except Exception as e:
            logger.error(f"Failed to cleanup S3 staging: {e}")
        
        # Local Cleanup
        import shutil
        if self.local_proc_dir.exists():
            shutil.rmtree(self.local_proc_dir)
            
        logger.info("Cleanup complete.")

    def run(self) -> None:
        """Executes the full compaction lifecycle."""
        if not self.acquire_lock():
            return
            
        try:
            moved = self.isolate_wal()
            if moved > 0:
                self.acquire_staging()
                self.merge()
                self.commit_remote()
                self.cleanup()
            else:
                logger.info("Nothing to compact.")
        finally:
            self.release_lock()
