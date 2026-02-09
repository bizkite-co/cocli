import os
import json
import logging
import time
from datetime import datetime, UTC
from typing import Any

import boto3
from botocore.exceptions import ClientError

from .config import get_cocli_base_dir

logger = logging.getLogger(__name__)

class CompactManager:
    """
    Implements the Freeze-Ingest-Merge-Commit (FIMC) pattern for sharded indexes.
    Uses S3-Native isolation to prevent race conditions with workers.
    """
    
    def __init__(self, campaign_name: str, index_name: str = "google_maps_prospects"):
        self.campaign_name = campaign_name
        self.index_name = index_name
        self.run_id = f"run_{int(time.time())}"
        
        # Local Paths
        self.data_root = get_cocli_base_dir() / "campaigns" / campaign_name
        self.index_dir = self.data_root / "indexes" / index_name
        self.checkpoint_path = self.index_dir / "prospects.checkpoint.usv"
        self.local_proc_dir = self.index_dir / "processing" / self.run_id
        
        # S3 Paths
        # prefix should not have leading slash for boto3
        self.s3_index_prefix = f"campaigns/{campaign_name}/indexes/{index_name}/"
        self.s3_wal_prefix = self.s3_index_prefix + "wal/"
        self.s3_proc_prefix = self.s3_index_prefix + f"processing/{self.run_id}/"
        self.s3_lock_key = self.s3_index_prefix + "compact.lock"
        
        # S3 Client (Lazy loaded)
        self._s3: Any = None
        self._bucket = "roadmap-cocli-data-use1" # TODO: Load from config

    @property
    def s3(self) -> Any:
        if self._s3 is None:
            # We assume local machine has proper creds/profile for compaction
            session = boto3.Session() 
            self._s3 = session.client("s3")
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
        """Moves files from wal/ to processing/run_id/ on S3."""
        logger.info(f"Isolating WAL files to {self.s3_proc_prefix}...")
        
        # 1. List current WAL
        paginator = self.s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=self._bucket, Prefix=self.s3_wal_prefix)
        
        to_move = []
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    key = obj['Key']
                    if key.endswith(".usv") or key.endswith(".csv"):
                        to_move.append(key)
        
        if not to_move:
            logger.info("No WAL files found to isolate.")
            return 0

        # 2. Atomic Move (Copy + Delete)
        # S3 doesn't have a native 'move', so we must copy then delete
        # We do this one by one or in small batches to ensure consistency
        moved_count = 0
        for old_key in to_move:
            rel_path = old_key[len(self.s3_wal_prefix):]
            new_key = self.s3_proc_prefix + rel_path
            
            try:
                # Copy
                self.s3.copy_object(
                    Bucket=self._bucket,
                    CopySource={'Bucket': self._bucket, 'Key': old_key},
                    Key=new_key
                )
                # Delete original
                self.s3.delete_object(Bucket=self._bucket, Key=old_key)
                moved_count += 1
            except Exception as e:
                logger.error(f"Failed to move {old_key}: {e}")

        logger.info(f"Isolated {moved_count} files.")
        return moved_count

    def acquire_staging(self) -> None:
        """Syncs the processing/run_id/ folder from S3 to local disk."""
        logger.info(f"Acquiring staging data to {self.local_proc_dir}...")
        
        # Ensure local dir exists
        self.local_proc_dir.mkdir(parents=True, exist_ok=True)
        
        # We use a simple sync logic here since we only care about this specific run_id
        paginator = self.s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=self._bucket, Prefix=self.s3_proc_prefix)
        
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    key = obj['Key']
                    rel_path = key[len(self.s3_proc_prefix):]
                    dest_path = self.local_proc_dir / rel_path
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    self.s3.download_file(self._bucket, key, str(dest_path))
        
        logger.info("Staging data acquired.")

    def merge(self) -> None:
        """Merges checkpoint and staging using DuckDB."""
        import duckdb
        logger.info("Starting DuckDB merge...")
        
        con = duckdb.connect(database=':memory:')
        
        # Use our standard 55-column schema from GoogleMapsProspect
        # We define it here explicitly to ensure the DuckDB binder is happy
        columns = {
            "place_id": "VARCHAR",
            "company_slug": "VARCHAR",
            "name": "VARCHAR",
            "phone_1": "VARCHAR",
            "created_at": "VARCHAR",
            "updated_at": "VARCHAR",
            "version": "INTEGER",
            "keyword": "VARCHAR",
            "full_address": "VARCHAR",
            "street_address": "VARCHAR",
            "city": "VARCHAR",
            "zip": "VARCHAR",
            "municipality": "VARCHAR",
            "state": "VARCHAR",
            "country": "VARCHAR",
            "timezone": "VARCHAR",
            "phone_standard_format": "VARCHAR",
            "website": "VARCHAR",
            "domain": "VARCHAR",
            "first_category": "VARCHAR",
            "second_category": "VARCHAR",
            "claimed_google_my_business": "VARCHAR",
            "reviews_count": "INTEGER",
            "average_rating": "DOUBLE",
            "hours": "VARCHAR",
            "saturday": "VARCHAR",
            "sunday": "VARCHAR",
            "monday": "VARCHAR",
            "tuesday": "VARCHAR",
            "wednesday": "VARCHAR",
            "thursday": "VARCHAR",
            "friday": "VARCHAR",
            "latitude": "DOUBLE",
            "longitude": "DOUBLE",
            "coordinates": "VARCHAR",
            "plus_code": "VARCHAR",
            "menu_link": "VARCHAR",
            "gmb_url": "VARCHAR",
            "cid": "VARCHAR",
            "google_knowledge_url": "VARCHAR",
            "kgmid": "VARCHAR",
            "image_url": "VARCHAR",
            "favicon": "VARCHAR",
            "review_url": "VARCHAR",
            "facebook_url": "VARCHAR",
            "linkedin_url": "VARCHAR",
            "instagram_url": "VARCHAR",
            "thumbnail_url": "VARCHAR",
            "reviews": "VARCHAR",
            "quotes": "VARCHAR",
            "uuid": "VARCHAR",
            "company_hash": "VARCHAR",
            "discovery_phrase": "VARCHAR",
            "discovery_tile_id": "VARCHAR",
            "processed_by": "VARCHAR"
        }

        tmp_checkpoint = self.checkpoint_path.with_suffix(".tmp")
        
        # 1. Gather all paths
        paths = []
        if self.checkpoint_path.exists():
            paths.append(str(self.checkpoint_path))
        
        # Add all staged USVs
        paths.extend([str(p) for p in self.local_proc_dir.rglob("*.usv")])
        
        if not paths:
            logger.info("No data found to merge.")
            return

        path_list = "', '".join(paths)
        
        # 2. Run the Deduplication Query
        # We sort by updated_at DESC and take the first one (latest)
        q = f"""
            COPY (
                SELECT * EXCLUDE (row_num) FROM (
                    SELECT *, 
                           row_number() OVER (PARTITION BY place_id ORDER BY updated_at DESC) as row_num
                    FROM read_csv(['{path_list}'], 
                                 delim='\x1f', 
                                 header=False, 
                                 columns={json.dumps(columns)}, 
                                 ignore_errors=True)
                ) 
                WHERE row_num = 1
            ) TO '{tmp_checkpoint}' (DELIMITER '\x1f', HEADER FALSE)
        """
        
        con.execute(q)
        
        # 3. Commit Local
        if tmp_checkpoint.exists():
            os.replace(tmp_checkpoint, self.checkpoint_path)
            logger.info(f"Merged checkpoint saved to {self.checkpoint_path}")
        
    def commit_remote(self) -> None:
        """Uploads the new checkpoint to S3."""
        logger.info("Uploading updated checkpoint to S3...")
        s3_key = self.s3_index_prefix + "prospects.checkpoint.usv"
        self.s3.upload_file(str(self.checkpoint_path), self._bucket, s3_key)
        logger.info("S3 Checkpoint updated.")

    def cleanup(self) -> None:
        """Purges staging data from local and remote."""
        logger.info("Cleaning up staging layers...")
        
        # 1. Remote Processing Dir
        paginator = self.s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=self._bucket, Prefix=self.s3_proc_prefix)
        
        to_delete = []
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    to_delete.append({'Key': obj['Key']})
        
        if to_delete:
            for i in range(0, len(to_delete), 1000):
                self.s3.delete_objects(Bucket=self._bucket, Delete={'Objects': to_delete[i:i+1000]})
        
        # 2. Local Processing Dir
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
