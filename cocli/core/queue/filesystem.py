import os
import json
import logging
from typing import List, Type, TypeVar, Any, cast, Optional
from pathlib import Path
from datetime import datetime, timedelta


from ...models.scrape_task import ScrapeTask, GmItemTask
from ...models.queue import QueueMessage
from ...core.config import get_cocli_base_dir, get_campaign_dir

logger = logging.getLogger(__name__)

T = TypeVar('T', ScrapeTask, GmItemTask, QueueMessage)

class FilesystemQueue:
    """
    A distributed-safe filesystem queue using atomic leases.
    Designed to work with S3-synced directories.
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
        
        self.campaign_dir = get_campaign_dir(campaign_name)
        if not self.campaign_dir:
            raise ValueError(f"Campaign directory not found for {campaign_name}")
            
        self.lease_dir = self.campaign_dir / "active-leases" / queue_name
        self.lease_dir.mkdir(parents=True, exist_ok=True)
        
        # We need a worker ID for the lease
        self.worker_id = os.getenv("HOSTNAME") or os.getenv("COMPUTERNAME") or "unknown-worker"

    def _get_lease_path(self, task_id: str) -> Path:
        # Sanitize task_id for filename
        safe_id = task_id.replace("/", "_").replace("\\", "_")
        return self.lease_dir / f"{safe_id}.lease"

    def _create_lease(self, task_id: str) -> bool:
        """Attempts to create an atomic lease file."""
        lease_path = self._get_lease_path(task_id)
        logger.debug(f"Worker {self.worker_id} attempting lease for {task_id} at {lease_path}")
        try:
            # os.O_CREAT | os.O_EXCL is atomic on most filesystems (including EFS/Local)
            fd = os.open(lease_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, 'w') as f:
                lease_data = {
                    "worker_id": self.worker_id,
                    "created_at": datetime.utcnow().isoformat(),
                    "heartbeat_at": datetime.utcnow().isoformat(),
                    "expires_at": (datetime.utcnow() + timedelta(minutes=self.lease_duration)).isoformat()
                }
                json.dump(lease_data, f)
            logger.debug(f"Worker {self.worker_id} acquired lease for {task_id}")
            return True
        except FileExistsError:
            logger.debug(f"Worker {self.worker_id} lease already exists for {task_id}")
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
            now = datetime.utcnow()
            
            is_expired = now > expires_at
            is_stale = (now - heartbeat_at).total_seconds() > (self.stale_heartbeat * 60)
            
            if is_expired or is_stale:
                logger.warning(f"Reclaiming stale/expired lease for {task_id} (Worker: {data.get('worker_id')})")
                try:
                    # To reclaim safely, we should ideally use a lock or just try to delete and re-create
                    # but since we are already in a "FileExists" state, we delete and then the NEXT poll will get it.
                    # Or we delete and try to create immediately.
                    lease_path.unlink()
                    return self._create_lease(task_id)
                except FileNotFoundError:
                    # Someone else already reclaimed it
                    return False
        except Exception as e:
            logger.error(f"Error checking stale lease for {task_id}: {e}")
        
        return False

    def push(self, task_id: str, payload: dict[str, Any]) -> str:
        """Writes a task to the frontier directory."""
        if not self.campaign_dir:
             raise ValueError("Campaign directory not set")
        frontier_dir = self.campaign_dir / "frontier" / self.queue_name
        frontier_dir.mkdir(parents=True, exist_ok=True)
        frontier_path = frontier_dir / f"{task_id}.json"
        
        # Only write if it doesn't exist (idempotent push)
        if not frontier_path.exists():
            # Use json.dumps with custom default or pydantic's dump
            # Since we receive a dict payload here (from model_dump), 
            # we need a custom encoder or convert back to model.
            # But the payload might already contain non-serializable objects.
            
            def datetime_handler(obj: Any) -> str:
                if isinstance(obj, datetime):
                    return obj.isoformat()
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

            with open(frontier_path, 'w') as f:
                json.dump(payload, f, default=datetime_handler)
            logger.debug(f"Pushed task {task_id} to {self.queue_name} frontier")
        return task_id

    def poll_frontier(self, task_type: Type[T], batch_size: int = 1) -> List[T]:
        """Generic poll for queues that use a 'frontier' directory for pushed tasks."""
        if not self.campaign_dir:
             return []
        frontier_dir = self.campaign_dir / "frontier" / self.queue_name
        if not frontier_dir.exists():
            return []
            
        tasks: List[T] = []
        count = 0
        # Sort by mtime to act like a queue
        for task_file in sorted(frontier_dir.glob("*.json"), key=lambda f: f.stat().st_mtime):
            if count >= batch_size:
                break
            
            task_id = task_file.stem
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
                    self.ack(task_id) # Remove lease if file is corrupt
        return tasks

    def ack(self, task_id: Optional[str]) -> None:
        """Deletes the lease file AND the frontier file."""
        if not task_id:
            return
        lease_path = self._get_lease_path(task_id)
        if not self.campaign_dir:
             return
        frontier_path = self.campaign_dir / "frontier" / self.queue_name / f"{task_id}.json"
        
        try:
            if lease_path.exists():
                lease_path.unlink()
            if frontier_path.exists():
                frontier_path.unlink()
        except Exception as e:
            logger.error(f"Error acking (deleting task/lease) for {task_id}: {e}")

    def heartbeat(self, task_id: str) -> None:
        """Updates the heartbeat timestamp of a lease."""
        lease_path = self._get_lease_path(task_id)
        if lease_path.exists():
            try:
                with open(lease_path, 'r') as f:
                    data = json.load(f)
                
                data['heartbeat_at'] = datetime.utcnow().isoformat()
                data['expires_at'] = (datetime.utcnow() + timedelta(minutes=self.lease_duration)).isoformat()
                
                with open(lease_path, 'w') as f:
                    json.dump(data, f)
                logger.debug(f"Heartbeat updated for {task_id}")
            except Exception as e:
                logger.error(f"Error updating heartbeat for {task_id}: {e}")

    def nack(self, task_id: Optional[str]) -> None:
        """Releases the lease without deleting the task, so it can be retried."""
        if not task_id:
            return
        lease_path = self._get_lease_path(task_id)
        try:
            if lease_path.exists():
                lease_path.unlink()
                logger.debug(f"Nacked (released lease) for {task_id}")
        except Exception as e:
            logger.error(f"Error nacking (releasing lease) for {task_id}: {e}")

class FilesystemGmListQueue(FilesystemQueue):
    """Specialized queue for Google Maps List scraping using the Mission Index."""

    def __init__(self, campaign_name: str):
        super().__init__(campaign_name, "gm-list")
        self.target_tiles_dir = cast(Path, self.campaign_dir) / "indexes" / "target-tiles"
        self.witness_dir = get_cocli_base_dir() / "indexes" / "scraped-tiles"

    def poll(self, batch_size: int = 1) -> List[ScrapeTask]:
        # ... (implementation remains same as before but uses ScrapeTask)
        tasks: List[ScrapeTask] = []
        if not self.target_tiles_dir.exists():
            return []

        count = 0
        for csv_path in self.target_tiles_dir.glob("**/*.csv"):
            task_id = str(csv_path.relative_to(self.target_tiles_dir))
            witness_path = self.witness_dir / task_id
            if witness_path.exists():
                continue
                
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
        # Note: GmList doesn't delete the target-tiles, just the lease
        if task.ack_token:
            lease_path = self._get_lease_path(task.ack_token)
            if lease_path.exists():
                lease_path.unlink()

class FilesystemGmDetailsQueue(FilesystemQueue):
    """Queue for Google Maps Details (Place IDs). Hisotry: 100% functional on local/residential IPs."""
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