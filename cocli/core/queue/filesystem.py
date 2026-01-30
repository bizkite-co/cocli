import os
import json
import logging
from typing import List, Type, TypeVar, Any, Optional, Union, Dict
from pathlib import Path
from datetime import datetime, timedelta, UTC
from botocore.exceptions import ClientError

from ...models.scrape_task import ScrapeTask, GmItemTask
from ...models.queue import QueueMessage
from ...core.config import get_cocli_base_dir, get_campaign_dir
from ...core.paths import paths

logger = logging.getLogger(__name__)

T = TypeVar('T', ScrapeTask, GmItemTask, QueueMessage)

class FilesystemQueue:
    """
    A distributed-safe filesystem queue using atomic leases (V2).
    Structure:
      queues/<campaign>/<queue>/
        pending/
          <shard>/
            <task_id>/
              task.json
              lease.json
        completed/
          <task_id>.json
    """

    def __init__(
        self,
        campaign_name: str,
        queue_name: str,
        lease_duration_minutes: int = 15,
        stale_heartbeat_minutes: int = 10,
        s3_client: Any = None,
        bucket_name: Optional[str] = None
    ):
        self.campaign_name = campaign_name
        self.queue_name = queue_name
        self.lease_duration = lease_duration_minutes
        self.stale_heartbeat = stale_heartbeat_minutes
        self.s3_client = s3_client
        self.bucket_name = bucket_name
        
        # New V2 Path: queues/<campaign>/<queue>
        self.queue_base = paths.queue(campaign_name, queue_name)
        logger.info(f"Initialized FilesystemQueue V2 for {queue_name} at {self.queue_base} (S3 Atomic: {s3_client is not None})")
        
        self.pending_dir = self.queue_base / "pending"
        self.completed_dir = self.queue_base / "completed"
        self.failed_dir = self.queue_base / "failed"
        
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self.completed_dir.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)
        
        # We need a worker ID for the lease
        self.worker_id = os.getenv("COCLI_HOSTNAME") or os.getenv("HOSTNAME") or os.getenv("COMPUTERNAME") or "unknown-worker"

    def _get_s3_lease_key(self, task_id: str) -> str:
        # V2 S3 Path matches the local structure under the campaign
        # Use first char as shard for better S3 performance and listing sharding
        shard = task_id[0] if task_id else "_"
        return f"campaigns/{self.campaign_name}/queues/{self.queue_name}/pending/{shard}/{task_id}/lease.json"

    def _get_s3_task_key(self, task_id: str) -> str:
        shard = task_id[0] if task_id else "_"
        return f"campaigns/{self.campaign_name}/queues/{self.queue_name}/pending/{shard}/{task_id}/task.json"

    def _get_task_dir(self, task_id: str) -> Path:
        # Sanitize task_id for directory name
        safe_id = task_id.replace("/", "_").replace("\\", "_")
        shard = safe_id[0] if safe_id else "_"
        return self.pending_dir / shard / safe_id

    def _get_lease_path(self, task_id: str) -> Path:
        return self._get_task_dir(task_id) / "lease.json"

    def _create_lease(self, task_id: str) -> bool:
        """Attempts to create an atomic lease (Local O_EXCL or S3 Conditional)."""
        now = datetime.now(UTC)
        lease_data = {
            "worker_id": self.worker_id,
            "created_at": now.isoformat(),
            "heartbeat_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=self.lease_duration)).isoformat()
        }

        # 1. Try S3 Conditional Write (Global Atomic)
        if self.s3_client and self.bucket_name:
            s3_key = self._get_s3_lease_key(task_id)
            try:
                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Body=json.dumps(lease_data),
                    IfNoneMatch='*',  # Atomic creation
                    # Store owner info in metadata for fast HEAD checks
                    Metadata={
                        'worker-id': self.worker_id,
                        'heartbeat-at': now.isoformat()
                    },
                    ContentType="application/json"
                )
                logger.debug(f"Worker {self.worker_id} acquired S3 lease for {task_id}")
                
                # Also create local lease
                self._create_local_lease(task_id, lease_data)
                return True
            except ClientError as e:
                if e.response['Error']['Code'] in ['PreconditionFailed', '412']:
                    # Lease exists, check if stale
                    return self._reclaim_stale_s3_lease(task_id)
                logger.error(f"S3 Lease Error for {task_id}: {e}")
                return False
            except Exception as e:
                # Fallback
                if "IfNoneMatch" in str(e):
                    logger.warning("S3 Conditional Write not supported. Falling back to local.")
                else:
                    logger.error(f"Unexpected S3 error: {e}")

        # 2. Fallback to Local Lease
        return self._create_local_lease(task_id, lease_data)

    def _reclaim_stale_s3_lease(self, task_id: str) -> bool:
        """Checks if S3 lease is stale and attempts to reclaim it."""
        s3_key = self._get_s3_lease_key(task_id)
        try:
            # Efficiently check metadata without body
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            metadata = response.get('Metadata', {})
            
            hb_str = metadata.get('heartbeat-at')
            if not hb_str:
                # Fallback to body if metadata missing (legacy leases)
                response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
                data = json.loads(response['Body'].read())
                hb_str = data.get('heartbeat_at')

            if hb_str:
                heartbeat_at = datetime.fromisoformat(hb_str).replace(tzinfo=UTC)
                now = datetime.now(UTC)
                
                if (now - heartbeat_at).total_seconds() > (self.stale_heartbeat * 60):
                    logger.warning(f"Reclaiming stale S3 lease for {task_id} (Worker: {metadata.get('worker-id')})")
                    # Atomic delete before reclaim
                    self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
                    return self._create_lease(task_id)
        except Exception as e:
            logger.error(f"Error reclaiming S3 lease for {task_id}: {e}")
        return False

    def _create_local_lease(self, task_id: str, lease_data: dict[str, Any]) -> bool:
        task_dir = self._get_task_dir(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        lease_path = task_dir / "lease.json"
        
        try:
            fd = os.open(lease_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, 'w') as f:
                json.dump(lease_data, f)
            return True
        except FileExistsError:
            return self._reclaim_stale_local_lease(task_id)
        except Exception as e:
            logger.error(f"Error creating local lease for {task_id}: {e}")
            return False

    def _reclaim_stale_local_lease(self, task_id: str) -> bool:
        # Renamed from _reclaim_stale_lease to avoid confusion
        lease_path = self._get_lease_path(task_id)
        try:
            with open(lease_path, 'r') as f:
                data = json.load(f)
            
            heartbeat_at = datetime.fromisoformat(data['heartbeat_at'])
            expires_at = datetime.fromisoformat(data['expires_at'])
            
            # Ensure they are aware
            if heartbeat_at.tzinfo is None:
                heartbeat_at = heartbeat_at.replace(tzinfo=UTC)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
                
            now = datetime.now(UTC)
            
            is_expired = now > expires_at
            is_stale = (now - heartbeat_at).total_seconds() > (self.stale_heartbeat * 60)
            
            if is_expired or is_stale:
                logger.warning(f"Reclaiming stale/expired lease for {task_id} (Worker: {data.get('worker_id')})")
                try:
                    lease_path.unlink()
                    return self._create_lease(task_id)
                except FileNotFoundError:
                    return False
        except Exception as e:
            logger.error(f"Error checking stale lease for {task_id}: {e}")
        
        return False

    def push(self, task_id: str, payload: dict[str, Any]) -> str:
        """Writes a task to the pending directory."""
        task_dir = self._get_task_dir(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        
        task_path = task_dir / "task.json"
        
        # Idempotent push: only write if not exists
        if not task_path.exists():
            def datetime_handler(obj: Any) -> str:
                if isinstance(obj, datetime):
                    return obj.isoformat()
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

            with open(task_path, 'w') as f:
                json.dump(payload, f, default=datetime_handler)
            logger.debug(f"Pushed task {task_id} to {self.queue_name} pending")
        return task_id

    def poll_frontier(self, task_type: Type[T], batch_size: int = 1) -> List[T]:
        """Generic poll for queues with S3 discovery fallback."""
        if not self.pending_dir.exists():
            self.pending_dir.mkdir(parents=True, exist_ok=True)
            
        tasks: List[T] = []
        count = 0
        
        # 1. Get local candidates
        candidates = []
        if self.pending_dir.exists():
            for entry in self.pending_dir.iterdir():
                if entry.is_dir():
                    # If it's a shard (single char), look inside
                    if len(entry.name) == 1:
                        for sub_entry in entry.iterdir():
                            if sub_entry.is_dir():
                                candidates.append(sub_entry)
                    else:
                        # Legacy/Flat structure
                        candidates.append(entry)
        
        # 2. If no local candidates and we have S3, try to discover some
        if not candidates and self.s3_client and self.bucket_name:
            logger.info(f"Local queue {self.queue_name} empty, discovering from S3...")
            self._discover_tasks_from_s3()
            # Re-scan after discovery
            for entry in self.pending_dir.iterdir():
                if entry.is_dir():
                    if len(entry.name) == 1:
                        for sub_entry in entry.iterdir():
                            if sub_entry.is_dir() and sub_entry not in candidates:
                                candidates.append(sub_entry)
                    elif entry not in candidates:
                        candidates.append(entry)

        # Shuffle to minimize collision in distributed environment (Randomized Sharding)
        import random
        random.shuffle(candidates)
        
        for task_dir in candidates:
            if count >= batch_size:
                break
                
            task_file = task_dir / "task.json"
            if not task_file.exists():
                # If directory exists but no task.json, it might be a partial sync or someone else's lease
                continue

            task_id = task_dir.name
            
            if self._create_lease(task_id):
                try:
                    with open(task_file, 'r') as f:
                        data = json.load(f)
                    task = task_type(**data)
                    task.ack_token = task_id
                    tasks.append(task)
                    count += 1
                except Exception as e:
                    logger.error(f"Error reading task file {task_file}: {e}")
                    self.nack(task_id) 
        return tasks

    def _discover_tasks_from_s3(self, max_discovery: int = 100) -> None:
        """Lists S3 to find pending tasks using Sharded FIFO Discovery."""
        if not self.s3_client or not self.bucket_name:
            return

        # 1. Discover which shards actually exist in S3
        pending_prefix = f"campaigns/{self.campaign_name}/queues/{self.queue_name}/pending/"
        shards = []
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=pending_prefix, Delimiter='/'):
                for prefix in page.get('CommonPrefixes', []):
                    shard = prefix.get('Prefix').split('/')[-2]
                    if shard:
                        shards.append(shard)
        except Exception as e:
            logger.error(f"Error listing shards from S3: {e}")
            return

        if not shards:
            return

        import random
        random.shuffle(shards)
        
        found_total = 0
        # Try a few active shards
        for shard in shards[:5]: 
            if found_total >= max_discovery:
                break
                
            prefix = f"campaigns/{self.campaign_name}/queues/{self.queue_name}/pending/{shard}/"
            try:
                # Recursive listing to see both task.json and lease.json in one call
                # No delimiter means we get the full keys under the prefix
                response = self.s3_client.list_objects_v2(
                    Bucket=self.bucket_name,
                    Prefix=prefix,
                    MaxKeys=500 
                )
                
                if 'Contents' not in response:
                    continue

                # 1. Group objects by Task ID and extract timestamps
                # Key structure: .../pending/<shard>/<task_id>/[task.json|lease.json]
                tasks_in_shard: Dict[str, Dict[str, Any]] = {}
                
                for obj in response['Contents']:
                    key = obj['Key']
                    parts = key.split('/')
                    if len(parts) < 2:
                        continue
                    
                    filename = parts[-1]
                    task_id = parts[-2]
                    
                    if task_id not in tasks_in_shard:
                        tasks_in_shard[task_id] = {"has_task": False, "has_lease": False, "mtime": None}
                    
                    if filename == "task.json":
                        tasks_in_shard[task_id]["has_task"] = True
                        tasks_in_shard[task_id]["mtime"] = obj['LastModified']
                    elif filename == "lease.json":
                        tasks_in_shard[task_id]["has_lease"] = True

                # 2. Filter for Available Tasks (Has task, No lease)
                available_tasks = [
                    (tid, info["mtime"]) 
                    for tid, info in tasks_in_shard.items() 
                    if info["has_task"] and not info["has_lease"]
                ]

                # 3. Sort by mtime (FIFO: Oldest First)
                available_tasks.sort(key=lambda x: x[1] if x[1] else datetime.min.replace(tzinfo=UTC))

                # 4. Download metadata for discovery
                for task_id, _ in available_tasks[:max_discovery - found_total]:
                    task_dir = self._get_task_dir(task_id)
                    task_file = task_dir / "task.json"
                    
                    if not task_file.exists():
                        task_dir.mkdir(parents=True, exist_ok=True)
                        s3_key = self._get_s3_task_key(task_id)
                        try:
                            self.s3_client.download_file(self.bucket_name, s3_key, str(task_file))
                            logger.debug(f"Discovered FIFO task {task_id} from shard {shard}")
                            found_total += 1
                        except Exception:
                            pass
            except Exception as e:
                logger.error(f"Error discovering tasks from S3 shard {shard}: {e}")

    def ack(self, task_id: Optional[str]) -> None:
        """Moves task to completed and removes pending directory (Local and S3)."""
        if not task_id:
            return
        
        task_dir = self._get_task_dir(task_id)
        task_file = task_dir / "task.json"
        completed_file = self.completed_dir / f"{task_id}.json"
        
        try:
            # 1. Local Cleanup
            if task_file.exists():
                task_file.rename(completed_file)
            
            import shutil
            if task_dir.exists():
                shutil.rmtree(task_dir, ignore_errors=True)
            
            # 2. S3 Cleanup & Completion (Immediate)
            if self.s3_client and self.bucket_name:
                s3_task_key = self._get_s3_task_key(task_id)
                s3_lease_key = self._get_s3_lease_key(task_id)
                s3_completed_key = f"campaigns/{self.campaign_name}/queues/{self.queue_name}/completed/{task_id}.json"
                
                # Upload completed file first
                if completed_file.exists():
                    self.s3_client.upload_file(str(completed_file), self.bucket_name, s3_completed_key)

                # Delete task and lease from pending
                self.s3_client.delete_objects(
                    Bucket=self.bucket_name,
                    Delete={
                        'Objects': [
                            {'Key': s3_task_key},
                            {'Key': s3_lease_key}
                        ]
                    }
                )
                logger.debug(f"Immediate S3 Ack for {task_id} completed.")
                
        except Exception as e:
            logger.error(f"Error acking for {task_id}: {e}")

    def heartbeat(self, task_id: str) -> None:
        """Updates the heartbeat timestamp of a lease using an efficient S3 self-copy."""
        lease_path = self._get_lease_path(task_id)
        now_dt = datetime.now(UTC)
        
        # 1. Update S3 (Immediate Metadata-only Copy)
        if self.s3_client and self.bucket_name:
            s3_key = self._get_s3_lease_key(task_id)
            try:
                # Refresh lease via self-copy (updates LastModified and Metadata)
                self.s3_client.copy_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    CopySource={'Bucket': self.bucket_name, 'Key': s3_key},
                    Metadata={
                        'worker-id': self.worker_id,
                        'heartbeat-at': now_dt.isoformat()
                    },
                    MetadataDirective='REPLACE',
                    ContentType="application/json"
                )
                logger.debug(f"S3 Heartbeat for {task_id} via CopyObject")
            except Exception as e:
                logger.error(f"Error updating S3 heartbeat for {task_id}: {e}")

        # 2. Update Local
        if lease_path.exists():
            try:
                with open(lease_path, 'r') as f:
                    data = json.load(f)
                
                data['heartbeat_at'] = now_dt.isoformat()
                data['expires_at'] = (now_dt + timedelta(minutes=self.lease_duration)).isoformat()
                
                with open(lease_path, 'w') as f:
                    json.dump(data, f)
            except Exception as e:
                logger.error(f"Error updating local heartbeat for {task_id}: {e}")

    def nack(self, task_or_id: Optional[Union[str, Any]]) -> None:
        """Releases the lease (Local and S3)."""
        if not task_or_id:
            return
            
        task_id = task_or_id if isinstance(task_or_id, str) else getattr(task_or_id, 'ack_token', None)
        if not task_id:
            return

        # 1. Local Cleanup
        lease_path = self._get_lease_path(task_id)
        try:
            if lease_path.exists():
                lease_path.unlink()
        except Exception as e:
            logger.error(f"Error local nacking for {task_id}: {e}")
            
        # 2. S3 Cleanup (Immediate)
        if self.s3_client and self.bucket_name:
            s3_key = self._get_s3_lease_key(task_id)
            try:
                self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
                logger.debug(f"Immediate S3 Nack for {task_id} completed.")
            except Exception as e:
                logger.error(f"Error S3 nacking for {task_id}: {e}")

class FilesystemGmListQueue(FilesystemQueue):
    """Specialized queue for Google Maps List scraping using the Mission Index."""

    def __init__(self, campaign_name: str, s3_client: Any = None, bucket_name: Optional[str] = None):
        super().__init__(campaign_name, "gm-list", s3_client=s3_client, bucket_name=bucket_name)
        self.campaign_dir = get_campaign_dir(campaign_name)
        if self.campaign_dir:
            self.target_tiles_dir = self.campaign_dir / "indexes" / "target-tiles"
        else:
            self.target_tiles_dir = Path("does-not-exist")
        self.witness_dir = get_cocli_base_dir() / "indexes" / "scraped-tiles"

    def push(self, task: ScrapeTask) -> str: # type: ignore[override]
        """
        Ensures the task exists in the Mission Index (target_tiles_dir).
        Since FilesystemGmListQueue polls the Mission Index directly, 
        pushing just means ensuring the file exists.
        """
        # ID format: lat/lon/phrase.csv
        from ..text_utils import slugify
        
        # Use consistent 1-decimal formatting for directory structure
        lat_dir = f"{task.latitude:.1f}"
        lon_dir = f"{task.longitude:.1f}"
        phrase_file = f"{slugify(task.search_phrase)}.csv"
        
        task_id = f"{lat_dir}/{lon_dir}/{phrase_file}"
        target_path = self.target_tiles_dir / task_id
        
        if not target_path.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "w") as f:
                f.write("latitude,longitude\n")
                f.write(f"{task.latitude},{task.longitude}\n")
            logger.debug(f"Pushed task to Mission Index: {task_id}")
            
            # If we have S3, also push it there
            if self.s3_client and self.bucket_name:
                try:
                    s3_key = f"campaigns/{self.campaign_name}/indexes/target-tiles/{task_id}"
                    self.s3_client.put_object(
                        Bucket=self.bucket_name, 
                        Key=s3_key, 
                        Body=f"latitude,longitude\n{task.latitude},{task.longitude}\n",
                        ContentType="text/csv"
                    )
                except Exception as e:
                    logger.warning(f"Failed to push tile to S3: {e}")
                    
        return task_id

    def poll(self, batch_size: int = 1) -> List[ScrapeTask]:
        tasks: List[ScrapeTask] = []
        
        # 1. Discover tasks from S3 if local is empty or we have S3 capability
        if self.s3_client and self.bucket_name:
            # We use a similar discovery logic but for the target-tiles index
            self._discover_mission_from_s3()

        if not self.target_tiles_dir.exists():
            return []

        count = 0
        import os
        import random

        # Optimization: Use os.walk for better performance on large mission indexes
        for root, dirs, files in os.walk(self.target_tiles_dir):
            if count >= batch_size:
                break

            # Randomize order to minimize collisions across cluster
            random.shuffle(dirs)
            random.shuffle(files)

            for file in files:
                if not file.endswith(".csv") and not file.endswith(".usv"):
                    continue
                
                csv_path = Path(root) / file
                task_id = str(csv_path.relative_to(self.target_tiles_dir))
                
                # Check witness (both .csv and .usv)
                witness_csv = self.witness_dir / Path(task_id).with_suffix(".csv")
                witness_usv = self.witness_dir / Path(task_id).with_suffix(".usv")
                if witness_csv.exists() or witness_usv.exists():
                    continue
                    
                # Try to acquire lease
                if self._create_lease(task_id):
                    parts = Path(task_id).parts
                    if len(parts) < 3:
                        continue
                    
                    try:
                        lat = float(parts[0])
                        lon = float(parts[1])
                        # Handle both .csv and .usv
                        phrase = parts[2].replace(".csv", "").replace(".usv", "")
                        
                        task = ScrapeTask(
                            latitude=lat,
                            longitude=lon,
                            zoom=15,
                            search_phrase=phrase,
                            campaign_name=self.campaign_name,
                            tile_id=f"{lat}_{lon}_{phrase}",
                            ack_token=task_id
                        )
                        tasks.append(task)
                        count += 1
                    except Exception as e:
                        logger.error(f"Error parsing task_id {task_id}: {e}")
                        self.nack(task_id)
                    
                if count >= batch_size:
                    break
        return tasks

    def _discover_mission_from_s3(self, max_discovery: int = 50) -> None:
        """Discovers unscraped tiles directly from the S3 Mission Index."""
        if not self.s3_client or not self.bucket_name:
            return

        prefix = f"campaigns/{self.campaign_name}/indexes/target-tiles/"
        try:
            # We list a small sample of the mission index on S3
            paginator = self.s3_client.get_paginator('list_objects_v2')
            found_count = 0
            
            # Since mission index is large, we pick a random starting point if possible,
            # or just take the first few pages.
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    if not key.endswith(".csv") and not key.endswith(".usv"):
                        continue
                        
                    rel_path = key.replace(prefix, "")
                    local_path = self.target_tiles_dir / rel_path
                    
                    if not local_path.exists():
                        # Check if already scraped (Witness Index)
                        witness_csv = self.witness_dir / Path(rel_path).with_suffix(".csv")
                        witness_usv = self.witness_dir / Path(rel_path).with_suffix(".usv")
                        
                        if not witness_csv.exists() and not witness_usv.exists():
                            # Check if currently leased on S3 (Optional optimization)
                            # For now, we'll just download it and let _create_lease handle the atomicity
                            local_path.parent.mkdir(parents=True, exist_ok=True)
                            self.s3_client.download_file(self.bucket_name, key, str(local_path))
                            found_count += 1
                            
                    if found_count >= max_discovery:
                        return
        except Exception as e:
            logger.error(f"Error discovering mission from S3: {e}")

    def ack(self, task: ScrapeTask) -> None: # type: ignore
        # Note: GmList doesn't move data, just removes the lease/dir
        if task.ack_token:
            # 1. Local Cleanup
            task_dir = self._get_task_dir(task.ack_token)
            import shutil
            if task_dir.exists():
                shutil.rmtree(task_dir, ignore_errors=True)
            
            # 2. S3 Cleanup (Immediate)
            if self.s3_client and self.bucket_name:
                try:
                    s3_lease_key = self._get_s3_lease_key(task.ack_token)
                    
                    # Upload a completion marker to S3 so reports can count it
                    # Sanitize task_id for S3 key (remove slashes)
                    safe_id = task.ack_token.replace("/", "_").replace("\\", "_")
                    s3_completed_key = f"campaigns/{self.campaign_name}/queues/{self.queue_name}/completed/{safe_id}.json"
                    
                    completion_data = {
                        "task_id": task.ack_token,
                        "completed_at": datetime.now(UTC).isoformat(),
                        "worker_id": self.worker_id
                    }
                    
                    self.s3_client.put_object(
                        Bucket=self.bucket_name,
                        Key=s3_completed_key,
                        Body=json.dumps(completion_data),
                        ContentType="application/json"
                    )

                    self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_lease_key)
                    logger.debug(f"Immediate S3 Ack for GmList {task.ack_token} completed.")
                except Exception as e:
                    logger.error(f"Error S3 acking for GmList {task.ack_token}: {e}")

class FilesystemGmDetailsQueue(FilesystemQueue):
    """Queue for Google Maps Details (Place IDs)."""
    def __init__(self, campaign_name: str, s3_client: Any = None, bucket_name: Optional[str] = None):
        super().__init__(campaign_name, "gm-details", s3_client=s3_client, bucket_name=bucket_name)

    def push(self, task: GmItemTask) -> str: # type: ignore
        task_id = super().push(task.place_id, task.model_dump())
        if self.s3_client and self.bucket_name:
            try:
                task_dir = self._get_task_dir(task.place_id)
                task_file = task_dir / "task.json"
                s3_key = self._get_s3_task_key(task.place_id)
                self.s3_client.upload_file(str(task_file), self.bucket_name, s3_key)
            except Exception as e:
                logger.error(f"Failed immediate S3 push for gm-details: {e}")
        return task_id

    def poll(self, batch_size: int = 1) -> List[GmItemTask]:
        return self.poll_frontier(GmItemTask, batch_size)

    def ack(self, task: Union[GmItemTask, str]) -> None: # type: ignore[override]
        token = task.ack_token if hasattr(task, 'ack_token') else task
        super().ack(token)

    def nack(self, task: Union[GmItemTask, str]) -> None: # type: ignore[override]
        token = task.ack_token if hasattr(task, 'ack_token') else task
        super().nack(token)

class FilesystemEnrichmentQueue(FilesystemQueue):
    """Queue for Website Enrichment."""
    def __init__(self, campaign_name: str, s3_client: Any = None, bucket_name: Optional[str] = None):
        super().__init__(campaign_name, "enrichment", s3_client=s3_client, bucket_name=bucket_name)

    def push(self, task: QueueMessage) -> str: # type: ignore
        # Use a hash of the company_slug + domain to avoid filesystem length limits
        import hashlib
        raw_id = f"{task.company_slug}_{task.domain}"
        task_id = hashlib.md5(raw_id.encode()).hexdigest()
        pushed_id = super().push(task_id, task.model_dump())
        
        if self.s3_client and self.bucket_name:
            try:
                task_dir = self._get_task_dir(task_id)
                task_file = task_dir / "task.json"
                s3_key = self._get_s3_task_key(task_id)
                self.s3_client.upload_file(str(task_file), self.bucket_name, s3_key)
            except Exception as e:
                logger.error(f"Failed immediate S3 push for enrichment: {e}")
        return pushed_id

    def poll(self, batch_size: int = 1) -> List[QueueMessage]:
        return self.poll_frontier(QueueMessage, batch_size)

    def ack(self, task: Union[QueueMessage, str]) -> None: # type: ignore[override]
        token = task.ack_token if hasattr(task, 'ack_token') else task
        super().ack(token)

    def nack(self, task: Union[QueueMessage, str]) -> None: # type: ignore[override]
        token = task.ack_token if hasattr(task, 'ack_token') else task
        super().nack(token)
