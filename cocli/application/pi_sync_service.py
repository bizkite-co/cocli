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

from cocli.core.config import get_campaign
from cocli.services.cluster_service import ClusterService
from cocli.core.paths import paths, QueuePaths


logger = logging.getLogger(__name__)

# Queue directories to sync from each Pi node.
# Each entry is (queue_name, remote_subpath, local_subpath_fn). pending/ is
# synced alongside completed/ so pending counts and lease state shown by
# `cocli stations inspect` reflect the live cluster instead of going stale
# for months (see cocli/commands/stations_cmd.py's warning about this same
# gap). gm-list widened from completed/results/ to the full completed/ for
# consistency with gm-details/enrichment - a no-op today (results/ is the
# only thing under it) but won't silently miss a future subdir.
_SYNC_QUEUES: list[tuple[str, str, Callable[[QueuePaths], Path]]] = [
    ("gm-list",    "completed/", lambda q: q / "completed"),
    ("gm-list",    "pending/",   lambda q: q / "pending"),
    ("gm-details", "completed/", lambda q: q / "completed"),
    ("gm-details", "pending/",   lambda q: q / "pending"),
    ("enrichment", "completed/", lambda q: q / "completed"),
    ("enrichment", "pending/",   lambda q: q / "pending"),
]


@dataclass
class SyncResult:
    """Result of a single node sync."""

    host: str
    success: bool
    files_synced: int
    error: str | None = None
    queue_results: dict[str, int] = field(default_factory=dict)


def describe_sync_results(results: list[SyncResult]) -> tuple[bool, str]:
    """Whether every configured node synced, and the text to show for that.

    An empty node list and a partial queue failure are both incomplete.
    Callers print a success line only when this returns True.
    """
    if not results:
        return False, "No Pi nodes configured."
    failed = [r for r in results if not r.success]
    if failed:
        lines: list[str] = []
        for result in failed:
            if result.error:
                lines.append(f"{result.host}: {result.error}")
                continue
            bad = [name for name, count in result.queue_results.items() if count < 0]
            detail = ", ".join(bad) if bad else "one or more queues failed"
            lines.append(f"{result.host}: {detail}")
        return False, "\n".join(lines)
    files = sum(r.files_synced for r in results)
    return True, f"{len(results)} nodes, {files} files"


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
        self.results: list[SyncResult] = []

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
                # queue_name alone isn't unique now that a queue can appear
                # twice (completed/ and pending/) - keying by name alone
                # would let the second entry silently clobber the first's
                # count in the report dict below.
                result_key = f"{queue_name} ({remote_subpath.rstrip('/')})"
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
                    queue_results[result_key] = synced
                    total_files += synced
                else:
                    error_msg = result.stderr.strip() or "Unknown error"
                    logger.warning(f"  {host}/{queue_name}: Failed - {error_msg}")
                    queue_results[result_key] = -1  # mark as failed

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

    def sync_all_nodes(self, blocking: bool = True) -> list[SyncResult]:
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

    def sync_prospect_wal_to_s3(self, index_name: str = "google_maps_prospects") -> list[SyncResult]:
        """
        Pushes each Pi node's local index WAL (e.g. add_to_wal() output written
        directly by scrapers) up to S3, via a local staging hop: rsync Pi -> a
        staging dir, then `aws s3 sync` staging -> S3's wal/ prefix.

        Must NOT land the rsync in the campaign's real local WAL dir
        (indexes/{index_name}/wal). isolate_wal() no longer deletes that
        directory (C9: purge only in cleanup() after commit), but staging
        still lives under the campaign root so a copy used only for the S3
        push cannot be mistaken for a fold source.

        Staging is cleared after a successful S3 push so already-pushed WAL
        entries aren't re-synced/re-uploaded on the next run. That rmtree is
        the S3-push copy under ``_pi_wal_staging/``, not Pi WAL and not
        ``index_dir/wal``.
        """
        import shutil

        from cocli.core.config import load_campaign_config
        from cocli.core.reporting import get_data_bucket_name

        config = load_campaign_config(self.campaign)
        aws_config = config.get("aws", {})
        bucket_name = get_data_bucket_name(config, self.campaign)
        profile = aws_config.get("profile") or aws_config.get("aws_profile")
        s3_prefix = f"campaigns/{self.campaign}/indexes/{index_name}/wal/"

        staging_root = paths.campaign(self.campaign).path / "_pi_wal_staging" / index_name

        results: list[SyncResult] = []
        for node in self.nodes:
            host = node.hostname
            target = node.ip_address if node.ip_address else host
            node_staging = staging_root / host
            os.makedirs(node_staging, exist_ok=True)

            try:
                remote_path = f"mstouffer@{target}:repos/data/campaigns/{self.campaign}/indexes/{index_name}/wal/"
                logger.info(f"  Syncing {index_name} WAL from {host}...")
                rsync_result = subprocess.run(
                    ["rsync", "-avzu", remote_path, str(node_staging) + "/"],
                    capture_output=True, text=True, timeout=3600,
                )
                if rsync_result.returncode != 0:
                    error_msg = rsync_result.stderr.strip() or "Unknown rsync error"
                    logger.warning(f"  {host}: WAL rsync failed - {error_msg}")
                    results.append(SyncResult(host=host, success=False, files_synced=0, error=error_msg))
                    continue

                staged_files = [p for p in node_staging.rglob("*.usv") if p.is_file()]
                if not staged_files:
                    results.append(SyncResult(host=host, success=True, files_synced=0))
                    continue

                env = os.environ.copy()
                if profile:
                    env["AWS_PROFILE"] = str(profile)
                push_result = subprocess.run(
                    ["aws", "s3", "sync", str(node_staging), f"s3://{bucket_name}/{s3_prefix}", "--quiet"],
                    capture_output=True, text=True, env=env, timeout=3600,
                )
                if push_result.returncode != 0:
                    error_msg = push_result.stderr.strip() or "Unknown S3 sync error"
                    logger.warning(f"  {host}: WAL push to S3 failed - {error_msg}")
                    results.append(SyncResult(host=host, success=False, files_synced=len(staged_files), error=error_msg))
                    continue

                shutil.rmtree(node_staging)
                logger.info(f"  {host}: Pushed {len(staged_files)} WAL files to S3.")
                results.append(SyncResult(host=host, success=True, files_synced=len(staged_files)))

            except subprocess.TimeoutExpired:
                logger.warning(f"  {host}: WAL sync timeout (>60 minutes)")
                results.append(SyncResult(host=host, success=False, files_synced=0, error="Timeout"))
            except Exception as e:
                logger.warning(f"  {host}: WAL sync error - {e}")
                results.append(SyncResult(host=host, success=False, files_synced=0, error=str(e)))

        return results

    def sync_email_indexes(self) -> list[SyncResult]:
        """Pull each worker's email index into this machine's email index.

        Enrichment writes emails only on the worker
        (EmailIndexManager.add_email). The customer CSV joins the local
        email index, and nothing else copies these files off the worker.
        ``rsync -au`` merges. ``--delete`` is omitted so one node's index
        cannot erase another node's files.
        """
        local_root = paths.campaign(self.campaign).path / "indexes" / "emails"
        os.makedirs(local_root, exist_ok=True)

        results: list[SyncResult] = []
        if not self.nodes:
            logger.warning("No Pi nodes configured")
            return results

        for node in self.nodes:
            host = node.hostname
            target = node.ip_address if node.ip_address else host
            remote_path = (
                f"mstouffer@{target}:repos/data/campaigns/{self.campaign}/indexes/emails/"
            )
            try:
                logger.info(f"  Syncing email index from {host}...")
                rsync_result = subprocess.run(
                    [
                        "rsync",
                        "-auz",
                        "--stats",
                        "-e",
                        "ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15",
                        remote_path,
                        str(local_root) + "/",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=3600,
                )
                if rsync_result.returncode != 0:
                    error_msg = rsync_result.stderr.strip() or "Unknown rsync error"
                    logger.warning(f"  {host}: email index rsync failed - {error_msg}")
                    results.append(
                        SyncResult(host=host, success=False, files_synced=0, error=error_msg)
                    )
                    continue
                transferred = 0
                for line in rsync_result.stdout.splitlines():
                    if line.startswith("Number of regular files transferred:"):
                        transferred = int(line.rsplit(":", 1)[-1].strip().replace(",", ""))
                        break
                logger.info(f"  {host}: email index sync transferred {transferred} paths.")
                results.append(SyncResult(host=host, success=True, files_synced=transferred))
            except subprocess.TimeoutExpired:
                logger.warning(f"  {host}: email index sync timeout (>60 minutes)")
                results.append(SyncResult(host=host, success=False, files_synced=0, error="Timeout"))
            except Exception as e:
                logger.warning(f"  {host}: email index sync error - {e}")
                results.append(SyncResult(host=host, success=False, files_synced=0, error=str(e)))

        return results

