import os
import json
import logging
from typing import List, Type, TypeVar, Any, Optional, Union
from pathlib import Path
from datetime import datetime, timedelta, UTC
from botocore.exceptions import ClientError

from ...models.scrape_task import ScrapeTask, GmItemTask
from ...models.queue import QueueMessage
from ...core.config import get_cocli_base_dir, get_campaign_dir

logger = logging.getLogger(__name__)

T = TypeVar('T', ScrapeTask, GmItemTask, QueueMessage)

class FilesystemQueue:
    """
    A distributed-safe filesystem queue using atomic leases (V2).
    Structure:
      data/queues/<campaign>/<queue>/
        pending/
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
        
        # New V2 Path: data/queues/<campaign>/<queue>
        self.queue_base = get_cocli_base_dir() / "data" / "queues" / campaign_name / queue_name
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
        return f"campaigns/{self.campaign_name}/queues/{self.queue_name}/pending/{task_id}/lease.json"

    def _get_task_dir(self, task_id: str) -> Path:
        # Sanitize task_id for directory name
        safe_id = task_id.replace("/", "_").replace("\\", "_")
        return self.pending_dir / safe_id

    def _get_lease_path(self, task_id: str) -> Path:
        return self._get_task_dir(task_id) / "lease.json"

    def _create_lease(self, task_id: str) -> bool:
        """Attempts to create an atomic lease (Local O_EXCL or S3 Conditional)."""
        lease_data = {
            "worker_id": self.worker_id,
            "created_at": datetime.now(UTC).isoformat(),
            "heartbeat_at": datetime.now(UTC).isoformat(),
            "expires_at": (datetime.now(UTC) + timedelta(minutes=self.lease_duration)).isoformat()
        }

        # 1. Try S3 Conditional Write (Global Atomic)
        if self.s3_client and self.bucket_name:
            s3_key = self._get_s3_lease_key(task_id)
            try:
                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Body=json.dumps(lease_data),
                    IfNoneMatch='*',  # This is the key for atomic creation
                    ContentType="application/json"
                )
                logger.debug(f"Worker {self.worker_id} acquired S3 lease for {task_id}")
                
                # Also create local lease to satisfy local checks/visibility
                self._create_local_lease(task_id, lease_data)
                return True
            except ClientError as e:
                if e.response['Error']['Code'] in ['PreconditionFailed', '412']:
                    # Lease exists, check if stale
                    return self._reclaim_stale_s3_lease(task_id)
                logger.error(f"S3 Lease Error for {task_id}: {e}")
                return False
            except Exception as e:
                # Fallback to local if S3 fails (e.g. older botocore version)
                if "IfNoneMatch" in str(e):
                    logger.warning("S3 Conditional Write not supported by this boto3/S3 version. Falling back to local leases.")
                else:
                    logger.error(f"Unexpected S3 error: {e}")

        # 2. Fallback to Local Lease (Atomic on same node, eventually consistent via sync)
        return self._create_local_lease(task_id, lease_data)

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

    def _reclaim_stale_s3_lease(self, task_id: str) -> bool:
        """Checks if S3 lease is stale and attempts to reclaim it."""
        s3_key = self._get_s3_lease_key(task_id)
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            data = json.loads(response['Body'].read())
            
            heartbeat_at = datetime.fromisoformat(data['heartbeat_at']).replace(tzinfo=UTC)
            now = datetime.now(UTC)
            
            if (now - heartbeat_at).total_seconds() > (self.stale_heartbeat * 60):
                logger.warning(f"Reclaiming stale S3 lease for {task_id} (Worker: {data.get('worker_id')})")
                # To reclaim safely, we should ideally use a conditional delete or overwrite with a version check
                # For now, just deleting and re-creating is better than nothing
                self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
                return self._create_lease(task_id)
        except Exception as e:
            logger.error(f"Error reclaiming S3 lease for {task_id}: {e}")
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
        candidates = [d for d in self.pending_dir.iterdir() if d.is_dir()]
        
        # 2. If no local candidates and we have S3, try to discover some
        if not candidates and self.s3_client and self.bucket_name:
            logger.info(f"Local queue {self.queue_name} empty, discovering from S3...")
            self._discover_tasks_from_s3()
            candidates = [d for d in self.pending_dir.iterdir() if d.is_dir()]

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
        """Lists S3 to find pending tasks and downloads their metadata."""
        if not self.s3_client or not self.bucket_name:
            return

        prefix = f"campaigns/{self.campaign_name}/queues/{self.queue_name}/pending/"
        try:
            # We only list a small batch to avoid massive memory/time usage
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                Delimiter='/', # We want the directories (task IDs)
                MaxKeys=max_discovery
            )
            
            if 'CommonPrefixes' in response:
                for cp in response['CommonPrefixes']:
                    full_prefix = cp['Prefix'] # e.g. .../pending/<task_id>/
                    task_id = full_prefix.split('/')[-2]
                    
                    task_dir = self._get_task_dir(task_id)
                    task_file = task_dir / "task.json"
                    
                    if not task_file.exists():
                        # Download the task.json
                        task_dir.mkdir(parents=True, exist_ok=True)
                        s3_key = f"{full_prefix}task.json"
                        try:
                            self.s3_client.download_file(self.bucket_name, s3_key, str(task_file))
                            logger.debug(f"Discovered and downloaded task {task_id} from S3")
                        except Exception:
                            # Might be a lease file without a task file yet
                            pass
        except Exception as e:
            logger.error(f"Error discovering tasks from S3: {e}")

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
            
            # 2. S3 Cleanup (Immediate)
            if self.s3_client and self.bucket_name:
                s3_task_key = f"campaigns/{self.campaign_name}/queues/{self.queue_name}/pending/{task_id}/task.json"
                s3_lease_key = self._get_s3_lease_key(task_id)
                
                # Delete task and lease
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
        """Updates the heartbeat timestamp of a lease (Local and S3)."""
        lease_path = self._get_lease_path(task_id)
        now_dt = datetime.now(UTC)
        
        # 1. Update S3 (Immediate)
        if self.s3_client and self.bucket_name:
            s3_key = self._get_s3_lease_key(task_id)
            try:
                # We need the full data to overwrite
                lease_data = {
                    "worker_id": self.worker_id,
                    "created_at": now_dt.isoformat(), # We don't have easy access to original created_at here without reading
                    "heartbeat_at": now_dt.isoformat(),
                    "expires_at": (now_dt + timedelta(minutes=self.lease_duration)).isoformat()
                }
                # Try to preserve created_at if local exists
                if lease_path.exists():
                    try:
                        with open(lease_path, 'r') as f:
                            local_data = json.load(f)
                        lease_data['created_at'] = local_data.get('created_at', lease_data['created_at'])
                    except Exception:
                        pass

                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Body=json.dumps(lease_data),
                    ContentType="application/json"
                )
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

    def nack(self, task_id: Optional[str]) -> None:
        """Releases the lease (Local and S3)."""
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

    def poll(self, batch_size: int = 1) -> List[ScrapeTask]:
        tasks: List[ScrapeTask] = []
        if not self.target_tiles_dir.exists():
            return []

        count = 0
        import os
        import random

        # Optimization: Use os.walk for better performance on large mission indexes (30k+ files)
        for root, dirs, files in os.walk(self.target_tiles_dir):
            if count >= batch_size:
                break

            # Randomize order to minimize collisions across cluster
            random.shuffle(dirs)
            random.shuffle(files)

            for file in files:
                if not file.endswith(".csv"):
                    continue
                
                csv_path = Path(root) / file
                task_id = str(csv_path.relative_to(self.target_tiles_dir))
                witness_path = self.witness_dir / task_id
                if witness_path.exists():
                    continue
                    
                # Try to acquire lease
                if self._create_lease(task_id):
                    parts = Path(task_id).parts
                    if len(parts) < 3:
                        continue
                    
                    try:
                        lat = float(parts[0])
                        lon = float(parts[1])
                        phrase = parts[2].replace(".csv", "")
                        
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
                s3_key = f"campaigns/{self.campaign_name}/queues/gm-details/pending/{task.place_id}/task.json"
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
                s3_key = f"campaigns/{self.campaign_name}/queues/enrichment/pending/{task_id}/task.json"
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
