import os
import json
import logging
from typing import List, Type, TypeVar, Any, Optional, Union, Dict
from pathlib import Path
from datetime import datetime, timedelta, UTC

from ...models.campaigns.queues.gm_list import ScrapeTask
from ...models.campaigns.queues.gm_details import GmItemTask
from ...models.campaigns.queues.base import QueueMessage
from ...core.config import get_cocli_base_dir, get_campaign_dir
from ...core.paths import paths
from ...core.sharding import get_shard_id
from .layout import QueueLayout, resolve_queue_station
from .task_file_filter import is_valid_task_data_file

logger = logging.getLogger(__name__)

T = TypeVar("T", ScrapeTask, GmItemTask, QueueMessage)


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

    Path construction (0010 PR2–PR3): phase dirs and S3 key roots come from
    :class:`QueueLayout` + PhaseRef so local and S3 share one relative scheme.
    Shard algorithm is the per-queue StationDecl combinator (place_id char or
    domain hash); ``_get_task_subpath`` still preserves pre-sharded task ids.
    """

    def __init__(
        self,
        campaign_name: str,
        queue_name: str,
        lease_duration_minutes: int = 15,
        stale_heartbeat_minutes: int = 10,
        s3_client: Any = None,
        bucket_name: Optional[str] = None,
        max_nack_attempts: int = 5,
    ):
        self.campaign_name = campaign_name
        self.queue_name = queue_name
        self.lease_duration = lease_duration_minutes
        self.stale_heartbeat = stale_heartbeat_minutes
        self.s3_client = s3_client
        self.bucket_name = bucket_name
        self.max_nack_attempts = max_nack_attempts

        if s3_client:
            logger.info(
                f"FilesystemQueue {queue_name} initialized WITH S3 client for bucket {bucket_name}"
            )
        else:
            logger.warning(
                f"FilesystemQueue {queue_name} initialized WITHOUT S3 client (Local-only mode)"
            )

        # New V2 Path: queues/<campaign>/<queue>
        self.queue_base = paths.queue(campaign_name, queue_name)
        logger.info(
            f"Initialized FilesystemQueue V2 for {queue_name} at {self.queue_base} (S3 Atomic: {s3_client is not None})"
        )

        # QueueLayout: per-queue StationDecl (PR3) + phase dirs; local≡S3 relative
        local_root = Path(str(self.queue_base.path))
        self.layout = QueueLayout(
            station=resolve_queue_station(queue_name),
            campaign_name=campaign_name,
            queue_name=queue_name,
            local_root=local_root,
        )
        ph = self.layout.phases
        self.pending_dir = self.layout.phase_dir(ph.pending)
        self.completed_dir = self.layout.phase_dir(ph.completed)
        self.failed_dir = self.layout.phase_dir(ph.failed)

        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self.completed_dir.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)

        # Enforce Frictionless Data Policy: Ensure authoritative queue datapackage.json sidecar exists
        self.ensure_schema_sidecar()

        # We need a worker ID for the lease
        self.worker_id = (
            os.getenv("COCLI_HOSTNAME")
            or os.getenv("HOSTNAME")
            or os.getenv("COMPUTERNAME")
            or "unknown-worker"
        )

    def ensure_schema_sidecar(self) -> None:
        """Writes authoritative datapackage.json sidecar for this queue via stations.schema."""
        try:
            from stations.schema import write_schema_sidecar
            schema = {
                "profile": "tabular-data-package",
                "name": self.queue_name,
                "resources": [
                    {
                        "name": self.queue_name,
                        "path": "**/*.json",
                        "format": "json",
                        "schema": {"fields": [{"name": "place_id", "type": "string"}, {"name": "domain", "type": "string"}]}
                    }
                ]
            }
            target_dir = Path(str(self.queue_base.path))
            target_dir.mkdir(parents=True, exist_ok=True)
            write_schema_sidecar(target_dir, schema, force=True, protect=True)
        except OSError as oe:
            logger.debug(f"Queue schema sidecar write skipped on read-only system for {self.queue_name}: {oe}")
        except Exception as e:
            logger.warning(f"Queue schema sidecar write failed for {self.queue_name}: {e}")

    def count_state(self, state: Union[str, Any]) -> int:
        """
        Count tasks/records in a queue state directory.
        Checks for valid data files (.usv and .json), ignoring metadata files.
        """
        state_str = str(state)
        state_dir = self.queue_base / state_str
        if not state_dir.exists():
            return 0

        total = 0
        for root, _, files in os.walk(state_dir):
            for f in files:
                if is_valid_task_data_file(f):
                    total += 1
        return total


    def _get_shard(self, task_id: str) -> str:
        """Shard from this queue's StationDecl combinator (0010 PR3).

        Place-id queues → ``shard_by_char_index(5)``; enrichment →
        ``shard_by_hash(2)``. Falls back to ``get_shard_id`` if no shard segment.
        """
        from stations.segments import collect_shard

        sh = collect_shard(self.layout.station.segments)
        if sh is not None:
            return sh.shard_for(task_id)
        return get_shard_id(task_id)

    def _get_task_subpath(self, task_id: str) -> str:
        """
        Returns the sharded relative path under a phase (e.g. 'a/ChIJ-123').
        Does **not** include the phase name (pending/...).

        Ensures the shard is only added if not already present in the task_id.
        """
        # Sanitize task_id for directory name
        safe_id = task_id.replace("\\", "/")

        # If task_id already looks like a sharded path (e.g. 2/25.0/...), return it as is.
        # We split and filter empty parts to handle leading/trailing slashes.
        parts = [p for p in safe_id.split("/") if p]
        if len(parts) > 1 and len(parts[0]) <= 2:
            last_part = parts[-1]
            for ext in [".usv", ".csv", ".json"]:
                if last_part.endswith(ext):
                    parts[-1] = last_part[:-len(ext)]
                    break
            return "/".join(parts)

        shard = self._get_shard(task_id)
        return f"{shard}/{safe_id}"

    def _pending_rel(self, task_id: str) -> str:
        """Relative path under queue root: ``pending/{subpath}``.

        Single string used for both local paths and S3 keys (0010 PR2).
        Phase name comes from StationDecl PhaseRef (still the string "pending"
        on disk — no format change).
        """
        pending = self.layout.phases.pending.name
        return f"{pending}/{self._get_task_subpath(task_id)}"

    def _s3_pending_prefix(self) -> str:
        """S3 list prefix for pending phase (trailing slash). Path-stable."""
        return f"{self.layout.s3_prefix()}/{self.layout.phases.pending.name}/"

    def _get_s3_lease_key(self, task_id: str) -> str:
        return f"{self.layout.s3_prefix()}/{self._pending_rel(task_id)}/lease.json"

    def _get_s3_task_key(self, task_id: str) -> str:
        return f"{self.layout.s3_prefix()}/{self._pending_rel(task_id)}/task.json"

    def _get_s3_completed_key(self, task_id: str) -> str:
        """Completed objects are flat under the phase (no shard) — production shape."""
        return (
            f"{self.layout.s3_prefix()}/"
            f"{self.layout.phases.completed.name}/{task_id}.json"
        )

    def _get_s3_failed_key(self, task_id: str) -> str:
        """Failed objects are flat under the phase (no shard) — production shape."""
        return (
            f"{self.layout.s3_prefix()}/"
            f"{self.layout.phases.failed.name}/{task_id}.json"
        )

    def _get_task_dir(self, task_id: str) -> Path:
        return self.layout.local_root / Path(self._pending_rel(task_id))

    def _get_lease_path(self, task_id: str) -> Path:
        return self._get_task_dir(task_id) / "lease.json"

    def _get_attempts_path(self, task_id: str) -> Path:
        return self._get_task_dir(task_id) / "attempts.json"

    def _record_nack_attempt(self, task_id: str) -> int:
        """Increments and returns the persistent nack count for a task."""
        attempts_path = self._get_attempts_path(task_id)
        count = 0
        try:
            if attempts_path.exists():
                with open(attempts_path, "r") as f:
                    count = json.load(f).get("count", 0)
        except Exception as e:
            logger.error(f"Error reading attempts file for {task_id}: {e}")

        count += 1

        try:
            with open(attempts_path, "w") as f:
                json.dump({"count": count}, f)
        except Exception as e:
            logger.error(f"Error writing attempts file for {task_id}: {e}")

        return count

    def _dead_letter(self, task_id: str, attempts: int) -> None:
        """Moves a task that has exceeded max_nack_attempts from pending to failed."""
        task_dir = self._get_task_dir(task_id)
        task_file = task_dir / "task.json"
        failed_file = self.failed_dir / f"{task_id}.json"

        logger.error(
            f"Task {task_id} in queue {self.queue_name} exceeded max nack attempts "
            f"({attempts}/{self.max_nack_attempts}). Dead-lettering to failed/."
        )

        try:
            # 1. Local: move task.json to failed/, remove the pending task dir entirely
            # (including its lease/attempts files) so it stops being a poll candidate.
            if task_file.exists():
                task_file.rename(failed_file)

            import shutil

            if task_dir.exists():
                shutil.rmtree(task_dir, ignore_errors=True)

            # 2. S3: mirror the move so other nodes discovering from S3 don't
            # re-download the same poison task.
            if self.s3_client and self.bucket_name:
                s3_task_key = self._get_s3_task_key(task_id)
                s3_lease_key = self._get_s3_lease_key(task_id)
                s3_failed_key = self._get_s3_failed_key(task_id)

                if failed_file.exists():
                    self.s3_client.upload_file(
                        str(failed_file), self.bucket_name, s3_failed_key
                    )

                self.s3_client.delete_objects(
                    Bucket=self.bucket_name,
                    Delete={"Objects": [{"Key": s3_task_key}, {"Key": s3_lease_key}]},
                )
        except Exception as e:
            logger.error(f"Error dead-lettering {task_id}: {e}")

    def _lease_payload(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        return {
            "worker_id": self.worker_id,
            "created_at": now.isoformat(),
            "heartbeat_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=self.lease_duration)).isoformat(),
        }

    def _lease_is_reclaimable(self, lease_bytes: bytes) -> bool:
        """Product reclaim predicate: expires_at or stale heartbeat (C3 uses CAS)."""
        try:
            data = json.loads(lease_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            return False
        if not isinstance(data, dict):
            return False
        now = datetime.now(UTC)

        exp_raw = data.get("expires_at")
        if isinstance(exp_raw, str):
            try:
                expires_at = datetime.fromisoformat(exp_raw.replace("Z", "+00:00"))
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
                if now > expires_at:
                    return True
            except ValueError:
                pass

        hb_raw = data.get("heartbeat_at")
        if isinstance(hb_raw, str):
            try:
                heartbeat_at = datetime.fromisoformat(hb_raw.replace("Z", "+00:00"))
                if heartbeat_at.tzinfo is None:
                    heartbeat_at = heartbeat_at.replace(tzinfo=UTC)
                if (now - heartbeat_at).total_seconds() > (self.stale_heartbeat * 60):
                    return True
            except ValueError:
                pass
        return False

    def _local_path_backend(self) -> Any:
        from stations.backends import LocalPathBackend

        # Absolute lease paths — no root sandbox (queue dirs already under data home)
        return LocalPathBackend()

    def _s3_path_backend(self) -> Any:
        from stations.backends import S3PathBackend

        assert self.s3_client is not None and self.bucket_name is not None
        return S3PathBackend(bucket=self.bucket_name, client=self.s3_client)

    def _create_lease(self, task_id: str) -> bool:
        """Atomic lease via stations PathBackend (create-if-absent, CAS reclaim)."""
        from stations.backends import acquire_lease

        lease_data = self._lease_payload()
        lease_bytes = json.dumps(lease_data).encode("utf-8")
        now = datetime.now(UTC)
        success = False
        tried_s3 = False

        # 1. S3 claim/reclaim (global atomic) through stations.backends
        if self.s3_client and self.bucket_name:
            tried_s3 = True
            s3_key = self._get_s3_lease_key(task_id)
            try:
                success = acquire_lease(
                    self._s3_path_backend(),
                    s3_key,
                    lease_bytes,
                    is_expired=self._lease_is_reclaimable,
                )
                if success:
                    logger.debug(
                        f"Worker {self.worker_id} acquired S3 lease for {task_id}"
                    )
                    # Mirror local lease for local workers (layout unchanged)
                    self._create_local_lease(task_id, lease_data)
            except Exception as e:
                if "IfNoneMatch" in str(e) or "IfMatch" in str(e):
                    logger.warning(
                        "S3 conditional write unsupported; falling back to local: %s",
                        e,
                    )
                    tried_s3 = False
                else:
                    logger.error(f"S3 Lease Error for {task_id}: {e}")
                    success = False

        # 2. Local claim/reclaim through stations.backends
        if not tried_s3 and not success:
            success = self._create_local_lease(task_id, lease_data)

        if success:
            try:
                from ..gossip_bridge import bridge

                if bridge and bridge.running:
                    from ...models.wal.record import QueueDatagram
                    from ..environment import get_environment

                    datagram = QueueDatagram(
                        campaign_name=self.campaign_name,
                        queue_name=self.queue_name,
                        task_id=task_id,
                        status="claimed",
                        timestamp=now.isoformat(),
                        node_id=self.worker_id,
                        environment=get_environment().value,
                    )
                    bridge.broadcast_msg(datagram.to_usv())
                    logger.debug(f"Broadcasted lease claim for {task_id}")
            except Exception as gossip_err:
                logger.debug(f"Gossip lease claim broadcast skipped: {gossip_err}")

        return success

    def _create_local_lease(self, task_id: str, lease_data: dict[str, Any]) -> bool:
        """Local lease via stations LocalPathBackend (O_EXCL + CAS reclaim, C3)."""
        from stations.backends import acquire_lease

        task_dir = self._get_task_dir(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        lease_path = str(self._get_lease_path(task_id))
        lease_bytes = json.dumps(lease_data).encode("utf-8")
        try:
            return acquire_lease(
                self._local_path_backend(),
                lease_path,
                lease_bytes,
                is_expired=self._lease_is_reclaimable,
            )
        except Exception as e:
            logger.error(f"Error creating local lease for {task_id}: {e}")
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

            with open(task_path, "w") as f:
                json.dump(payload, f, default=datetime_handler)
            logger.debug(f"Pushed task {task_id} to {self.queue_name} pending")
        return task_id

    def poll_frontier(self, task_type: Type[T], batch_size: int = 1) -> List[T]:
        """Generic poll for queues with S3 discovery fallback."""
        logger.info(f"Polling {self.queue_name} for tasks...")
        if not self.pending_dir.exists():
            self.pending_dir.mkdir(parents=True, exist_ok=True)

        tasks: List[T] = []
        count = 0

        # 1. Get local candidates
        candidates = []
        if self.pending_dir.exists():
            for entry in self.pending_dir.iterdir():
                if entry.is_dir():
                    # If it's a shard (1 or 2 chars), look inside
                    if len(entry.name) in [1, 2]:
                        for sub_entry in entry.iterdir():
                            if sub_entry.is_dir():
                                candidates.append(sub_entry)
                    else:
                        # Legacy/Flat structure
                        candidates.append(entry)

        logger.debug(
            f"Queue {self.queue_name}: Found {len(candidates)} local candidates."
        )
        # 2. If no local candidates and we have S3, try to discover some
        if not candidates and self.s3_client and self.bucket_name:
            # We don't log 'Local queue empty' every time to avoid spam
            # but we do need to try discovery
            self._discover_tasks_from_s3()
            # Re-scan after discovery
            for entry in self.pending_dir.iterdir():
                if entry.is_dir():
                    if len(entry.name) in [1, 2]:
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
                    with open(task_file, "r") as f:
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
            logger.warning(
                f"S3 Discovery for {self.queue_name} skipped: Missing S3 client ({self.s3_client is not None}) or Bucket ({self.bucket_name})"
            )
            return

        # 1. Discover which shards actually exist in S3
        pending_prefix = self._s3_pending_prefix()
        logger.info(
            f"S3 Discovery: Listing {self.bucket_name} with prefix {pending_prefix}"
        )
        shards = []
        try:
            paginator = self.s3_client.get_paginator("list_objects_v2")
            for page in paginator.paginate(
                Bucket=self.bucket_name, Prefix=pending_prefix, Delimiter="/"
            ):
                for prefix in page.get("CommonPrefixes", []):
                    shard_prefix = prefix.get("Prefix")
                    shard = shard_prefix.split("/")[-2]
                    if shard:
                        shards.append(shard)
            logger.info(
                f"Discovered {len(shards)} shards on S3 for {self.queue_name}: {shards}"
            )
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

            prefix = f"{self._s3_pending_prefix()}{shard}/"
            try:
                # Recursive listing to see both task.json and lease.json in one call
                # No delimiter means we get the full keys under the prefix
                response = self.s3_client.list_objects_v2(
                    Bucket=self.bucket_name, Prefix=prefix, MaxKeys=500
                )

                if "Contents" not in response:
                    continue

                # 1. Group objects by Task ID and extract timestamps
                # Key structure: .../pending/<shard>/<task_id>/[task.json|lease.json]
                tasks_in_shard: Dict[str, Dict[str, Any]] = {}

                for obj in response["Contents"]:
                    key = obj["Key"]
                    parts = key.split("/")
                    if len(parts) < 2:
                        continue

                    filename = parts[-1]
                    task_id = parts[-2]

                    if task_id not in tasks_in_shard:
                        tasks_in_shard[task_id] = {
                            "has_task": False,
                            "has_lease": False,
                            "mtime": None,
                        }

                    if filename == "task.json":
                        tasks_in_shard[task_id]["has_task"] = True
                        tasks_in_shard[task_id]["mtime"] = obj["LastModified"]
                    elif filename == "lease.json":
                        tasks_in_shard[task_id]["has_lease"] = True

                # 2. Filter for Available Tasks (Has task, No lease)
                available_tasks = [
                    (tid, info["mtime"])
                    for tid, info in tasks_in_shard.items()
                    if info["has_task"] and not info["has_lease"]
                ]
                logger.info(
                    f"Shard {shard}: Found {len(tasks_in_shard)} total task dirs, {len(available_tasks)} available (unleased)."
                )

                # 3. Sort by mtime (FIFO: Oldest First)
                available_tasks.sort(
                    key=lambda x: x[1] if x[1] else datetime.min.replace(tzinfo=UTC)
                )

                # 4. Download metadata for discovery
                for task_id, _ in available_tasks[: max_discovery - found_total]:
                    task_dir = self._get_task_dir(task_id)
                    task_file = task_dir / "task.json"

                    if not task_file.exists():
                        task_dir.mkdir(parents=True, exist_ok=True)
                        s3_key = self._get_s3_task_key(task_id)
                        try:
                            self.s3_client.download_file(
                                self.bucket_name, s3_key, str(task_file)
                            )
                            logger.debug(
                                f"Discovered FIFO task {task_id} from shard {shard}"
                            )
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
                s3_completed_key = self._get_s3_completed_key(task_id)

                # Upload completed file first
                if completed_file.exists():
                    self.s3_client.upload_file(
                        str(completed_file), self.bucket_name, s3_completed_key
                    )

                # Delete task and lease from pending
                self.s3_client.delete_objects(
                    Bucket=self.bucket_name,
                    Delete={"Objects": [{"Key": s3_task_key}, {"Key": s3_lease_key}]},
                )
                logger.debug(f"Immediate S3 Ack for {task_id} completed.")

            # 3. Broadcast progress via Gossip
            try:
                from ..gossip_bridge import bridge

                if bridge and bridge.running:
                    from ...models.wal.record import QueueDatagram
                    from ..environment import get_environment

                    datagram = QueueDatagram(
                        campaign_name=self.campaign_name,
                        queue_name=self.queue_name,
                        task_id=task_id,
                        status="completed",
                        timestamp=datetime.now(UTC).isoformat(),
                        node_id=self.worker_id,
                        environment=get_environment().value,
                    )
                    bridge.broadcast_msg(datagram.to_usv())
                    logger.debug(f"Broadcasted completion for {task_id}")
            except Exception as gossip_err:
                logger.debug(f"Gossip broadcast skipped: {gossip_err}")

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
                    CopySource={"Bucket": self.bucket_name, "Key": s3_key},
                    Metadata={
                        "worker-id": self.worker_id,
                        "heartbeat-at": now_dt.isoformat(),
                    },
                    MetadataDirective="REPLACE",
                    ContentType="application/json",
                )
                logger.debug(f"S3 Heartbeat for {task_id} via CopyObject")
            except Exception as e:
                logger.error(f"Error updating S3 heartbeat for {task_id}: {e}")

        # 2. Update Local
        if lease_path.exists():
            try:
                with open(lease_path, "r") as f:
                    data = json.load(f)

                data["heartbeat_at"] = now_dt.isoformat()
                data["expires_at"] = (
                    now_dt + timedelta(minutes=self.lease_duration)
                ).isoformat()

                with open(lease_path, "w") as f:
                    json.dump(data, f)
            except Exception as e:
                logger.error(f"Error updating local heartbeat for {task_id}: {e}")

    def nack(self, task_or_id: Optional[Union[str, Any]]) -> None:
        """Releases the lease (Local and S3)."""
        if not task_or_id:
            return

        task_id = (
            task_or_id
            if isinstance(task_or_id, str)
            else getattr(task_or_id, "ack_token", None)
        )
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

        # 3. Track repeated failures; dead-letter poison tasks so they stop
        # occupying a poll slot forever and stop blocking fresh S3 discovery
        # (poll_frontier only re-discovers from S3 when local candidates is
        # empty - a task that's never removed from pending/ blocks that
        # indefinitely).
        attempts = self._record_nack_attempt(task_id)
        dead_lettered = attempts >= self.max_nack_attempts
        if dead_lettered:
            self._dead_letter(task_id, attempts)

        # 4. Broadcast release via Gossip
        try:
            from ..gossip_bridge import bridge
            if bridge and bridge.running:
                from ...models.wal.record import QueueDatagram
                from ..environment import get_environment
                datagram = QueueDatagram(
                    campaign_name=self.campaign_name,
                    queue_name=self.queue_name,
                    task_id=task_id,
                    status="failed" if dead_lettered else "released",
                    timestamp=datetime.now(UTC).isoformat(),
                    node_id=self.worker_id,
                    environment=get_environment().value,
                )
                bridge.broadcast_msg(datagram.to_usv())
                logger.debug(f"Broadcasted lease release for {task_id}")
        except Exception as gossip_err:
            logger.debug(f"Gossip lease release broadcast skipped: {gossip_err}")


from cocli.core.geo_types import LatScale1, LonScale1


class FilesystemGmListQueue(FilesystemQueue):
    """Specialized queue for Google Maps List scraping using the Mission Index."""

    def __init__(
        self,
        campaign_name: str,
        s3_client: Any = None,
        bucket_name: Optional[str] = None,
        max_nack_attempts: int = 5,
    ):
        super().__init__(
            campaign_name,
            "gm-list",
            s3_client=s3_client,
            bucket_name=bucket_name,
            max_nack_attempts=max_nack_attempts,
        )
        self.campaign_dir = get_campaign_dir(campaign_name)
        if self.campaign_dir:
            from ..paths import paths

            self.discovery_gen_queue = paths.campaign(campaign_name).queue(
                "discovery-gen"
            )
            self.target_tiles_dir = self.discovery_gen_queue.completed
        else:
            self.target_tiles_dir = Path("does-not-exist")
        self.witness_dir = get_cocli_base_dir() / "indexes" / "scraped-tiles"

    def _create_scrape_task(self, task_id: str) -> Optional[ScrapeTask]:
        """Reconstructs a ScrapeTask from a discovery-gen task_id."""
        path_parts = Path(task_id).parts
        # Expected: {lat_shard}/{lat}/{lon}/{phrase}.usv
        if len(path_parts) != 4:
            return None

        try:
            lat = LatScale1(float(path_parts[1]))
            lon = LonScale1(float(path_parts[2]))
            phrase = path_parts[3].replace(".usv", "").replace(".csv", "")

            return ScrapeTask(
                latitude=lat,
                longitude=lon,
                zoom=15,
                search_phrase=phrase,
                campaign_name=self.campaign_name,
                tile_id=f"{lat}_{lon}",
                ack_token=task_id,
            )
        except Exception as e:
            logger.error(f"Error reconstructing ScrapeTask from {task_id}: {e}")
            return None

    def push(self, task: ScrapeTask) -> str:  # type: ignore[override]
        """
        Ensures the task exists in the Discovery Gen completed index.
        """
        from ..sharding import get_geo_shard, get_grid_tile_id
        from ..text_utils import slugify

        # OMAP Shard: shard/lat/lon/phrase.usv
        lat_shard = get_geo_shard(float(task.latitude))
        grid_id = get_grid_tile_id(float(task.latitude), float(task.longitude))
        lat_dir, lon_dir = grid_id.split("_")
        phrase_file = f"{slugify(task.search_phrase)}.usv"

        task_id = f"{lat_shard}/{lat_dir}/{lon_dir}/{phrase_file}"
        target_path = self.target_tiles_dir / task_id

        if not target_path.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "w") as f:
                # Use standard model-based serialization
                f.write(task.to_usv())
            logger.debug(f"Pushed task to Discovery Gen: {task_id}")

            # If we have S3, also push it there
            # INTENTIONAL EXCEPTION (PR7): discovery-gen is a separate station/pool,
            # not this queue's StationDecl layout.
            if self.s3_client and self.bucket_name:
                try:
                    s3_key = (
                        f"campaigns/{self.campaign_name}/queues/"
                        f"discovery-gen/completed/{task_id}"
                    )
                    self.s3_client.put_object(
                        Bucket=self.bucket_name,
                        Key=s3_key,
                        Body=task.to_usv(),  # Use model's standardized USV
                        ContentType="text/csv",
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
            logger.warning(
                f"Target tiles directory does not exist: {self.target_tiles_dir}"
            )
            return []

        logger.debug(f"Polling discovery-gen pool at: {self.target_tiles_dir}")
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

                # OMAP Violation Check: Detect deep legacy paths (more than 4 parts: shard/lat/lon/phrase)
                # Blueprint: {lat_shard}/{lat}/{lon}/{phrase}.csv
                parts = task_id.split(os.sep)
                if len(parts) > 4:
                    logger.warning(
                        f"DEPRECATED PATH DETECTED: {task_id}. Please run scripts/cleanup_queue_paths.py"
                    )
                    continue

                # Check witness (both .csv and .usv)
                witness_csv = self.witness_dir / Path(task_id).with_suffix(".csv")
                witness_usv = self.witness_dir / Path(task_id).with_suffix(".usv")
                if witness_csv.exists() or witness_usv.exists():
                    continue

                # Try to acquire lease
                if self._create_lease(task_id):
                    task = self._create_scrape_task(task_id)
                    if task:
                        tasks.append(task)
                        count += 1
                    else:
                        self.nack(task_id)

                if count >= batch_size:
                    break
        return tasks

    def _discover_mission_from_s3(self, max_discovery: int = 50) -> None:
        """Discovers unscraped tiles directly from the S3 Discovery Gen Index."""
        if not self.s3_client or not self.bucket_name:
            return

        # INTENTIONAL EXCEPTION (PR7): discovery-gen pool, not gm-list layout.
        prefix = f"campaigns/{self.campaign_name}/queues/discovery-gen/completed/"
        try:
            # We list a small sample of the mission index on S3
            paginator = self.s3_client.get_paginator("list_objects_v2")
            found_count = 0

            # Since mission index is large, we pick a random starting point if possible,
            # or just take the first few pages.
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if not key.endswith(".csv") and not key.endswith(".usv"):
                        continue

                    rel_path = key.replace(prefix, "")
                    local_path = self.target_tiles_dir / rel_path

                    if not local_path.exists():
                        # Check if already scraped (Witness Index)
                        witness_csv = self.witness_dir / Path(rel_path).with_suffix(
                            ".csv"
                        )
                        witness_usv = self.witness_dir / Path(rel_path).with_suffix(
                            ".usv"
                        )

                        if not witness_csv.exists() and not witness_usv.exists():
                            # Check if currently leased on S3 (Optional optimization)
                            # For now, we'll just download it and let _create_lease handle the atomicity
                            local_path.parent.mkdir(parents=True, exist_ok=True)
                            self.s3_client.download_file(
                                self.bucket_name, key, str(local_path)
                            )
                            found_count += 1

                    if found_count >= max_discovery:
                        return
        except Exception as e:
            logger.error(f"Error discovering mission from S3: {e}")

    def ack(self, task: ScrapeTask) -> None:  # type: ignore
        # Note: GmList doesn't move data, just removes the lease/dir
        if task.ack_token:
            # 1. Capture Lease Metadata before deletion
            lease_data = {}
            lease_path = self._get_lease_path(task.ack_token)
            if lease_path.exists():
                try:
                    with open(lease_path, "r") as f:
                        lease_data = json.load(f)
                except Exception:
                    pass

            # 2. Local Cleanup
            task_dir = self._get_task_dir(task.ack_token)
            import shutil

            if task_dir.exists():
                shutil.rmtree(task_dir, ignore_errors=True)

            # 3. Completion Receipt (Local & S3)
            # Use model's own sharded path resolution
            from ..geo_types import LatScale1, LonScale1
            from ..text_utils import slugify

            lat_t = (
                task.latitude
                if isinstance(task.latitude, LatScale1)
                else LatScale1(float(task.latitude))
            )
            lon_t = (
                task.longitude
                if isinstance(task.longitude, LonScale1)
                else LonScale1(float(task.longitude))
            )
            phrase_slug = slugify(task.search_phrase)

            completion_data = {
                "task_id": task.ack_token,
                "completed_at": datetime.now(UTC).isoformat(),
                "worker_id": lease_data.get("worker_id", self.worker_id),
                "lease_created_at": lease_data.get("created_at"),
                "search_phrase": task.search_phrase,
                "latitude": float(task.latitude),
                "longitude": float(task.longitude),
                "result_count": task.result_count,
                "metadata": getattr(
                    task, "metadata", {}
                ),  # Include audited metadata if present
            }

            # Local path (product shape: completed/results/{geo}/… — not DFQ flat)
            from ..sharding import get_geo_shard

            lat_shard = get_geo_shard(str(task.latitude))
            receipt_dir = (
                self.completed_dir / "results" / lat_shard / str(lat_t) / str(lon_t)
            )
            receipt_dir.mkdir(parents=True, exist_ok=True)
            receipt_path = receipt_dir / f"{phrase_slug}.json"

            with open(receipt_path, "w") as f:
                json.dump(completion_data, f, indent=2)

            # S3 Mirror — same relative tree under layout.s3_prefix()
            if self.s3_client and self.bucket_name:
                try:
                    s3_lease_key = self._get_s3_lease_key(task.ack_token)
                    s3_completed_key = self._get_s3_gm_list_result_key(
                        lat_shard, str(lat_t), str(lon_t), phrase_slug
                    )

                    self.s3_client.put_object(
                        Bucket=self.bucket_name,
                        Key=s3_completed_key,
                        Body=json.dumps(completion_data, indent=2),
                        ContentType="application/json",
                    )

                    self.s3_client.delete_object(
                        Bucket=self.bucket_name, Key=s3_lease_key
                    )
                    logger.debug(
                        f"Immediate S3 Ack for GmList {task.ack_token} completed."
                    )
                except Exception as e:
                    logger.error(f"Error S3 acking for GmList {task.ack_token}: {e}")

    def _get_s3_gm_list_result_key(
        self, lat_shard: str, lat_t: str, lon_t: str, phrase_slug: str
    ) -> str:
        """Product receipt path under completed/ (not base flat completed/{id}.json)."""
        completed = self.layout.phases.completed.name
        return (
            f"{self.layout.s3_prefix()}/{completed}/results/"
            f"{lat_shard}/{lat_t}/{lon_t}/{phrase_slug}.json"
        )


class FilesystemGmDetailsQueue(FilesystemQueue):
    """Queue for Google Maps Details (Place IDs)."""

    def __init__(
        self,
        campaign_name: str,
        s3_client: Any = None,
        bucket_name: Optional[str] = None,
        max_nack_attempts: int = 5,
    ):
        super().__init__(
            campaign_name,
            "gm-details",
            s3_client=s3_client,
            bucket_name=bucket_name,
            max_nack_attempts=max_nack_attempts,
        )

    def push(self, task: GmItemTask) -> str:  # type: ignore
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

    def ack(self, task: Union[GmItemTask, str]) -> None:  # type: ignore[override]
        token = task.ack_token if hasattr(task, "ack_token") else task
        super().ack(token)

    def nack(self, task: Union[GmItemTask, str]) -> None:  # type: ignore[override]
        token = task.ack_token if hasattr(task, "ack_token") else task
        super().nack(token)


class FilesystemEnrichmentQueue(FilesystemQueue):
    """Queue for Website Enrichment.

    Pending paths: layout + domain-hash StationDecl (same as base FSQ).
    Completed S3: product nested shape ``completed/{shard}/{domain}/task.json``
    (override of base flat completed/{id}.json) — matches production S3.
    """

    def __init__(
        self,
        campaign_name: str,
        s3_client: Any = None,
        bucket_name: Optional[str] = None,
        max_nack_attempts: int = 5,
    ):
        super().__init__(
            campaign_name,
            "enrichment",
            s3_client=s3_client,
            bucket_name=bucket_name,
            max_nack_attempts=max_nack_attempts,
        )

    def _get_task_model(self, task_id: str, data: Dict[str, Any]) -> Any:
        from ...models.campaigns.queues.enrichment import EnrichmentTask

        return EnrichmentTask(**data)

    def _get_s3_completed_key(self, task_id: str) -> str:
        """Production nested completed (not base flat completed/{id}.json)."""
        shard = self._get_shard(task_id)
        return (
            f"{self.layout.s3_prefix()}/"
            f"{self.layout.phases.completed.name}/{shard}/{task_id}/task.json"
        )

    def push(self, message: Union[QueueMessage, Any]) -> str:  # type: ignore
        from ...models.campaigns.queues.enrichment import EnrichmentTask

        # Upgrade QueueMessage to EnrichmentTask to get Ordinant properties
        if isinstance(message, EnrichmentTask):
            task = message
        else:
            task = EnrichmentTask(**message.model_dump())

        task_id = task.task_id
        shard = self._get_shard(task_id)

        # Use super().push with the deterministic task_id
        pushed_id = super().push(task_id, task.model_dump())

        if self.s3_client and self.bucket_name:
            try:
                task_dir = self._get_task_dir(task_id)
                task_file = task_dir / "task.json"
                # Single authority: queue layout builders (not model bypass)
                s3_key = self._get_s3_task_key(task_id)

                self.s3_client.upload_file(str(task_file), self.bucket_name, s3_key)
                logger.debug(f"Pushed Enrichment task {task_id} to S3 shard {shard}")
            except Exception as e:
                logger.error(f"Failed immediate S3 push for enrichment {task_id}: {e}")
        return pushed_id

    def poll(self, batch_size: int = 1) -> List[QueueMessage]:
        return self.poll_frontier(QueueMessage, batch_size)

    def ack(self, task: Union[QueueMessage, str]) -> None:  # type: ignore[override]
        token = task.ack_token if hasattr(task, "ack_token") else task
        if not token:
            return
        # super.ack uses _get_s3_completed_key (nested) + base pending cleanup
        super().ack(token)

    def nack(self, task: Union[QueueMessage, str]) -> None:  # type: ignore[override]
        token = task.ack_token if hasattr(task, "ack_token") else task
        if not token:
            return

        # 1. Local Cleanup
        super().nack(token)

        # 2. S3 Cleanup (Correct Path)
        if self.s3_client and self.bucket_name:
            s3_key = self._get_s3_lease_key(token)
            try:
                self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
                logger.debug(f"Immediate S3 Nack for {token} completed.")
            except Exception as e:
                logger.error(f"Error S3 nacking for {token}: {e}")


class FilesystemTileQueue:
    """
    Queue for atomic tile work units (map-tile).

    Phases (StationDecl): pending, processing, completed.
    Layout under pending: ``tiles/`` holds payload files (not a lifecycle phase).

    Path construction (0010 PR5): phase dirs and S3 prefix via QueueLayout +
    PhaseRef. On-disk shape unchanged: pending/tiles/, processing/, completed/.
    """

    def __init__(
        self,
        campaign_name: str,
        s3_client: Any = None,
        bucket_name: Optional[str] = None,
    ):
        from cocli.station_defs.campaigns.queues import (
            MAP_TILE_PENDING_LAYOUT,
            MAP_TILE_QUEUE_STATION,
        )
        from .layout import QueueLayout

        self.campaign_name = campaign_name
        self.queue_name = "map-tile"
        self.s3_client = s3_client
        self.bucket_name = bucket_name
        self.worker_id = (
            os.getenv("COCLI_HOSTNAME")
            or os.getenv("HOSTNAME")
            or os.getenv("COMPUTERNAME")
            or "unknown-worker"
        )

        if s3_client:
            logger.info(
                f"FilesystemTileQueue initialized WITH S3 client for bucket {bucket_name}"
            )
        else:
            logger.warning(
                "FilesystemTileQueue initialized WITHOUT S3 client (Local-only mode)"
            )

        self.queue_base = paths.queue(campaign_name, self.queue_name)
        local_root = Path(str(self.queue_base.path))
        self.layout = QueueLayout(
            station=MAP_TILE_QUEUE_STATION,
            campaign_name=campaign_name,
            queue_name=self.queue_name,
            local_root=local_root,
        )
        ph = self.layout.phases
        self.pending_dir = self.layout.phase_dir(ph.pending)
        self.completed_dir = self.layout.phase_dir(ph.completed)
        self._processing_phase = ph.processing
        self._pending_layout_name = MAP_TILE_PENDING_LAYOUT

        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self.completed_dir.mkdir(parents=True, exist_ok=True)
        self.processing_dir.mkdir(parents=True, exist_ok=True)

        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Ensures datapackage.json exists in pending/tiles from TileRecord schema."""
        from ...models.campaigns.tile import TileRecord

        tiles_dir = self.tiles_dir
        tiles_dir.mkdir(parents=True, exist_ok=True)

        # Create datapackage.json from TileRecord schema
        TileRecord.save_datapackage(tiles_dir, "tiles", "*.usv", force=False)
        logger.info(f"Tile queue schema ensured at {tiles_dir}")

    @property
    def tiles_dir(self) -> Path:
        """Payload bag under pending (layout segment, not a phase)."""
        return self.pending_dir / self._pending_layout_name

    @property
    def processing_dir(self) -> Path:
        """Active-like phase for tiles currently being worked on."""
        return self.layout.phase_dir(self._processing_phase)

    def _get_s3_completed_key(self, tile_filename: str) -> str:
        """S3 key for a completed tile file (flat under completed phase)."""
        completed = self.layout.phases.completed.name
        return f"{self.layout.s3_prefix()}/{completed}/{tile_filename}"

    def push(self, tile_file_path: Path) -> None:
        """Register a tile file in the queue (file should already exist in pending/tiles)."""
        if not tile_file_path.exists():
            raise FileNotFoundError(f"Tile file not found: {tile_file_path}")
        logger.debug(f"Registered tile: {tile_file_path.name}")

    def ack(self, task: Union[str, Path]) -> None:
        """Move tile file from processing → completed."""
        tile_file = Path(task) if isinstance(task, str) else task
        if not tile_file.exists():
            logger.warning(f"Tile file not found for ack: {tile_file}")
            return

        # Move from processing to completed
        completed_path = self.completed_dir / tile_file.name
        completed_path.parent.mkdir(parents=True, exist_ok=True)
        tile_file.rename(completed_path)
        logger.info(f"Tile completed and moved: {tile_file.name}")

        # Remove lease if it exists
        lease_path = self.processing_dir / f"{tile_file.name}.lease.json"
        if lease_path.exists():
            lease_path.unlink()

        # Optional: Push to S3 if configured
        if self.s3_client and self.bucket_name:
            try:
                s3_key = self._get_s3_completed_key(tile_file.name)
                with open(completed_path, "r") as f:
                    self.s3_client.put_object(
                        Bucket=self.bucket_name,
                        Key=s3_key,
                        Body=f.read(),
                        ContentType="text/csv",
                    )
            except Exception as e:
                logger.warning(f"Failed to push completed tile to S3: {e}")

        # Broadcast tile completion via Gossip
        try:
            from ..gossip_bridge import bridge
            if bridge and bridge.running:
                from ...models.wal.record import QueueDatagram
                from ..environment import get_environment
                datagram = QueueDatagram(
                    campaign_name=self.campaign_name,
                    queue_name=self.queue_name,
                    task_id=tile_file.name,
                    status="completed",
                    timestamp=datetime.now(UTC).isoformat(),
                    node_id=self.worker_id,
                    environment=get_environment().value,
                )
                bridge.broadcast_msg(datagram.to_usv())
                logger.debug(f"Broadcasted tile completion for {tile_file.name}")
        except Exception as gossip_err:
            logger.debug(f"Gossip tile completion broadcast skipped: {gossip_err}")

    def nack(self, task: Union[str, Path]) -> None:
        """Move tile file from processing back to pending/tiles."""
        tile_file = Path(task) if isinstance(task, str) else task

        # If passed a Path, use its name; otherwise use the string directly
        tile_filename = tile_file.name if isinstance(tile_file, Path) else tile_file
        processing_path = self.processing_dir / tile_filename

        if not processing_path.exists():
            logger.warning(f"Tile file not found in processing: {processing_path}")
            return

        # Move back to pending/tiles
        pending_path = self.tiles_dir / tile_filename
        pending_path.parent.mkdir(parents=True, exist_ok=True)
        processing_path.rename(pending_path)
        logger.info(f"Tile nacked and returned to pending: {tile_filename}")

        # Remove lease if it exists
        lease_path = self.processing_dir / f"{tile_filename}.lease.json"
        if lease_path.exists():
            lease_path.unlink()

        # Broadcast tile release via Gossip
        try:
            from ..gossip_bridge import bridge
            if bridge and bridge.running:
                from ...models.wal.record import QueueDatagram
                from ..environment import get_environment
                datagram = QueueDatagram(
                    campaign_name=self.campaign_name,
                    queue_name=self.queue_name,
                    task_id=tile_filename,
                    status="released",
                    timestamp=datetime.now(UTC).isoformat(),
                    node_id=self.worker_id,
                    environment=get_environment().value,
                )
                bridge.broadcast_msg(datagram.to_usv())
                logger.debug(f"Broadcasted tile release for {tile_filename}")
        except Exception as gossip_err:
            logger.debug(f"Gossip tile release broadcast skipped: {gossip_err}")
