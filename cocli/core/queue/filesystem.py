import os
import json
import logging
from typing import List, Type, TypeVar, Any, Optional
from pathlib import Path
from datetime import datetime, timedelta, UTC

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
        stale_heartbeat_minutes: int = 10
    ):
        self.campaign_name = campaign_name
        self.queue_name = queue_name
        self.lease_duration = lease_duration_minutes
        self.stale_heartbeat = stale_heartbeat_minutes
        
        # New V2 Path: data/queues/<campaign>/<queue>
        self.queue_base = get_cocli_base_dir() / "data" / "queues" / campaign_name / queue_name
        logger.info(f"Initialized FilesystemQueue V2 for {queue_name} at {self.queue_base}")
        
        self.pending_dir = self.queue_base / "pending"
        self.completed_dir = self.queue_base / "completed"
        self.failed_dir = self.queue_base / "failed"
        
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self.completed_dir.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)
        
        # We need a worker ID for the lease
        self.worker_id = os.getenv("HOSTNAME") or os.getenv("COMPUTERNAME") or "unknown-worker"

    def _get_task_dir(self, task_id: str) -> Path:
        # Sanitize task_id for directory name
        safe_id = task_id.replace("/", "_").replace("\\", "_")
        return self.pending_dir / safe_id

    def _get_lease_path(self, task_id: str) -> Path:
        return self._get_task_dir(task_id) / "lease.json"

    def _create_lease(self, task_id: str) -> bool:
        """Attempts to create an atomic lease file."""
        task_dir = self._get_task_dir(task_id)
        # Ensure the directory exists (it should for pending tasks, but for GmList we might need to make it)
        task_dir.mkdir(parents=True, exist_ok=True)
        
        lease_path = task_dir / "lease.json"
        
        logger.debug(f"Worker {self.worker_id} attempting lease for {task_id} at {lease_path}")
        try:
            # os.O_CREAT | os.O_EXCL is atomic on most filesystems (including EFS/Local)
            fd = os.open(lease_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, 'w') as f:
                lease_data = {
                    "worker_id": self.worker_id,
                    "created_at": datetime.now(UTC).isoformat(),
                    "heartbeat_at": datetime.now(UTC).isoformat(),
                    "expires_at": (datetime.now(UTC) + timedelta(minutes=self.lease_duration)).isoformat()
                }
                json.dump(lease_data, f)
            logger.debug(f"Worker {self.worker_id} acquired lease for {task_id}")
            return True
        except FileExistsError:
            # Check if existing lease is stale
            return self._reclaim_stale_lease(task_id)
        except Exception as e:
            logger.error(f"Error creating lease for {task_id}: {e}")
            return False

    def _reclaim_stale_lease(self, task_id: str) -> bool:
        """Checks if an existing lease is stale and attempts to reclaim it."""
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
        """Generic poll for queues."""
        if not self.pending_dir.exists():
            return []
            
        tasks: List[T] = []
        count = 0
        
        # Get all directories
        candidates = [d for d in self.pending_dir.iterdir() if d.is_dir()]
        
        # Shuffle to minimize collision in distributed environment (Randomized Sharding)
        import random
        random.shuffle(candidates)
        
        for task_dir in candidates:
            if count >= batch_size:
                break
                
            task_file = task_dir / "task.json"
            if not task_file.exists():
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
                    # If corrupt, maybe nack or move to failed? 
                    # For now, let's just release the lease so it can be inspected or retried
                    self.nack(task_id) 
        return tasks

    def ack(self, task_id: Optional[str]) -> None:
        """Moves task to completed and removes pending directory."""
        if not task_id:
            return
        
        task_dir = self._get_task_dir(task_id)
        task_file = task_dir / "task.json"
        completed_file = self.completed_dir / f"{task_id}.json"
        
        try:
            if task_file.exists():
                task_file.rename(completed_file)
            
            # Remove the lease and the directory
            import shutil
            if task_dir.exists():
                shutil.rmtree(task_dir, ignore_errors=True)
                
        except Exception as e:
            logger.error(f"Error acking for {task_id}: {e}")

    def heartbeat(self, task_id: str) -> None:
        """Updates the heartbeat timestamp of a lease."""
        lease_path = self._get_lease_path(task_id)
        if lease_path.exists():
            try:
                with open(lease_path, 'r') as f:
                    data = json.load(f)
                
                data['heartbeat_at'] = datetime.now(UTC).isoformat()
                data['expires_at'] = (datetime.now(UTC) + timedelta(minutes=self.lease_duration)).isoformat()
                
                with open(lease_path, 'w') as f:
                    json.dump(data, f)
            except Exception as e:
                logger.error(f"Error updating heartbeat for {task_id}: {e}")

    def nack(self, task_id: Optional[str]) -> None:
        """Releases the lease."""
        if not task_id:
            return
        lease_path = self._get_lease_path(task_id)
        try:
            if lease_path.exists():
                lease_path.unlink()
                logger.debug(f"Nacked (released lease) for {task_id}")
        except Exception as e:
            logger.error(f"Error nacking for {task_id}: {e}")

class FilesystemGmListQueue(FilesystemQueue):
    """Specialized queue for Google Maps List scraping using the Mission Index."""

    def __init__(self, campaign_name: str):
        super().__init__(campaign_name, "gm-list")
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
        for csv_path in self.target_tiles_dir.glob("**/*.csv"):
            task_id = str(csv_path.relative_to(self.target_tiles_dir))
            witness_path = self.witness_dir / task_id
            if witness_path.exists():
                continue
                
            # Try to acquire lease (this will create pending/<hash>/lease.json)
            if self._create_lease(task_id):
                parts = Path(task_id).parts
                if len(parts) < 3:
                    continue
                
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
                
            if count >= batch_size:
                break
        return tasks

    def ack(self, task: ScrapeTask) -> None: # type: ignore
        # Note: GmList doesn't move data, just removes the lease/dir
        if task.ack_token:
            task_dir = self._get_task_dir(task.ack_token)
            import shutil
            if task_dir.exists():
                shutil.rmtree(task_dir, ignore_errors=True)

class FilesystemGmDetailsQueue(FilesystemQueue):
    """Queue for Google Maps Details (Place IDs)."""
    def __init__(self, campaign_name: str):
        super().__init__(campaign_name, "gm-details")

    def push(self, task: GmItemTask) -> str: # type: ignore
        return super().push(task.place_id, task.model_dump())

    def poll(self, batch_size: int = 1) -> List[GmItemTask]:
        return self.poll_frontier(GmItemTask, batch_size)

    def ack(self, task: GmItemTask) -> None: # type: ignore
        super().ack(task.ack_token)

    def nack(self, task: GmItemTask) -> None: # type: ignore
        super().nack(task.ack_token)

class FilesystemEnrichmentQueue(FilesystemQueue):
    """Queue for Website Enrichment."""
    def __init__(self, campaign_name: str):
        super().__init__(campaign_name, "enrichment")

    def push(self, task: QueueMessage) -> str: # type: ignore
        # Use a hash of the company_slug + domain to avoid filesystem length limits
        import hashlib
        raw_id = f"{task.company_slug}_{task.domain}"
        task_id = hashlib.md5(raw_id.encode()).hexdigest()
        return super().push(task_id, task.model_dump())

    def poll(self, batch_size: int = 1) -> List[QueueMessage]:
        return self.poll_frontier(QueueMessage, batch_size)

    def ack(self, task: QueueMessage) -> None: # type: ignore
        super().ack(task.ack_token)

    def nack(self, task: QueueMessage) -> None: # type: ignore
        super().nack(task.ack_token)
