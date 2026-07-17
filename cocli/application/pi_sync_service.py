"""
PiSyncService: Background sync of queue results from Pi workers.
"""

import logging
import os
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from cocli.core.config import get_campaign
from cocli.services.cluster_service import ClusterService
from cocli.core.paths import paths, QueuePaths


logger = logging.getLogger(__name__)

# Queue directories to sync from each Pi node.
# Each entry is (queue_name, remote_subpath, local_subpath_fn).
_SYNC_QUEUES: list[tuple[str, str, Callable[[QueuePaths], Path]]] = [
    ("gm-list",    "completed/results/", lambda q: q / "completed" / "results"),
    ("gm-details", "completed/",         lambda q: q / "completed"),
    ("enrichment", "completed/",         lambda q: q / "completed"),
]


@dataclass
class SyncResult:
    """Result of a single node sync."""

    host: str
    success: bool
    files_synced: int
    error: str | None = None
    queue_results: dict[str, int] = field(default_factory=dict)


class PiSyncService:
    """
    Syncs queue results from Pi workers to local storage.

    Syncs the following queues from each node:
      - gm-list/completed/results/
      - gm-details/completed/
      - enrichment/completed/

    Usage:
        service = PiSyncService("roadmap")
        results = service.sync_all_nodes(blocking=True)
    """

    def __init__(self, campaign_name: str | None = None) -> None:
        campaign = campaign_name or get_campaign()
        if not campaign:
            raise ValueError("Campaign name is required")
        self.campaign: str = campaign

        cluster_service = ClusterService(self.campaign)
        self.nodes = cluster_service.get_nodes()
        self.results: List[SyncResult] = []

    def sync_node(self, host: str) -> SyncResult:
        """
        Sync results from a single node across all configured queues.

        Args:
            host: The hostname of the Pi (e.g., "cocli5x1.pi")

        Returns:
            SyncResult with total files synced across all queues.
        """
        try:
            node_info = next((n for n in self.nodes if n.hostname == host), None)
            target = (
                node_info.ip_address if node_info and node_info.ip_address else host
            )

            total_files = 0
            queue_results: dict[str, int] = {}

            for queue_name, remote_subpath, local_subpath_fn in _SYNC_QUEUES:
                remote_path = (
                    f"mstouffer@{target}:repos/data/campaigns/{self.campaign}"
                    f"/queues/{queue_name}/{remote_subpath}"
                )
                local_queue_root = paths.campaign(self.campaign).queue(queue_name)
                local_path = str(local_subpath_fn(local_queue_root))

                os.makedirs(local_path, exist_ok=True)

                cmd = [
                    "rsync",
                    "-avzu",
                    remote_path,
                    local_path + "/",
                ]

                logger.info(f"  Syncing {queue_name} from {host}...")
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )

                if result.returncode == 0:
                    output_lines = result.stdout.strip().split("\n")
                    synced = sum(
                        1
                        for line in output_lines
                        if line.startswith(".") or "/" in line and not line.endswith("/")
                    )
                    queue_results[queue_name] = synced
                    total_files += synced
                else:
                    error_msg = result.stderr.strip() or "Unknown error"
                    logger.warning(f"  {host}/{queue_name}: Failed - {error_msg}")
                    queue_results[queue_name] = -1  # mark as failed

            all_ok = all(v >= 0 for v in queue_results.values())
            logger.info(f"  {host}: {'Success' if all_ok else 'Partial'} ({total_files} files)")
            return SyncResult(
                host=host,
                success=all_ok,
                files_synced=total_files,
                queue_results=queue_results,
            )

        except subprocess.TimeoutExpired:
            logger.warning(f"  {host}: Timeout (>5 minutes)")
            return SyncResult(host=host, success=False, files_synced=0, error="Timeout")
        except Exception as e:
            logger.warning(f"  {host}: Error - {e}")
            return SyncResult(host=host, success=False, files_synced=0, error=str(e))

    def sync_all_nodes(self, blocking: bool = True) -> List[SyncResult]:
        """
        Sync from all configured Pi nodes.

        Args:
            blocking: If True, wait for all syncs to complete.

        Returns:
            List of SyncResult for each node.
        """
        self.results = []

        if not self.nodes:
            logger.warning("No Pi nodes configured")
            return []

        with ThreadPoolExecutor(max_workers=len(self.nodes)) as executor:
            futures = {
                executor.submit(self.sync_node, node.hostname): node.hostname
                for node in self.nodes
            }

            if blocking:
                for future in as_completed(futures):
                    result = future.result()
                    self.results.append(result)
            else:
                for host in futures.values():
                    self.results.append(
                        SyncResult(host=host, success=True, files_synced=0)
                    )

        return self.results

    def get_summary(self) -> dict[str, int]:
        """Get a summary of sync results."""
        total = len(self.results)
        successful = sum(1 for r in self.results if r.success)
        total_files = sum(r.files_synced for r in self.results)

        return {
            "total_nodes": total,
            "successful": successful,
            "failed": total - successful,
            "total_files_synced": total_files,
        }

