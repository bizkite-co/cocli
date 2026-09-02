"""
Lease cleanup utility: purge expired or stale leases from queue directories.

Stale leases can block work from being claimed. This utility finds and removes
lease.json files that are either expired (past heartbeat_at timeout) or
optionally forces removal of all leases for testing/reset scenarios.
"""

import logging
import json
from pathlib import Path
from datetime import datetime, UTC, timedelta

logger = logging.getLogger(__name__)


def purge_expired_leases(
    queue_dir: Path,
    max_heartbeat_age_minutes: int = 30,
    dry_run: bool = False,
) -> dict[str, int]:
    """
    Remove expired lease files from a queue directory.

    A lease is considered expired if its heartbeat_at timestamp is older than
    max_heartbeat_age_minutes. This indicates the worker holding the lease
    is no longer alive or processing.

    Args:
        queue_dir: Root queue directory (e.g., gm-list/pending/)
        max_heartbeat_age_minutes: Lease is stale if heartbeat older than this
        dry_run: If True, don't delete files, just count them

    Returns:
        Metrics: {leases_found, leases_expired, leases_deleted, errors}
    """
    leases_found = 0
    leases_expired = 0
    leases_deleted = 0
    errors = 0

    if not queue_dir.exists():
        logger.warning(f"Queue directory not found: {queue_dir}")
        return {
            "leases_found": 0,
            "leases_expired": 0,
            "leases_deleted": 0,
            "errors": 0,
        }

    now = datetime.now(UTC)
    cutoff_time = now - timedelta(minutes=max_heartbeat_age_minutes)

    logger.info(f"Scanning for expired leases in {queue_dir}")
    logger.info(f"  Cutoff: {cutoff_time.isoformat()} (leases older than {max_heartbeat_age_minutes} min)")

    # Walk through queue structure looking for lease.json files
    import os

    for root, dirs, files in os.walk(queue_dir):
        for filename in files:
            if filename == "lease.json":
                lease_path = Path(root) / filename
                leases_found += 1

                try:
                    with open(lease_path, "r") as f:
                        lease_data = json.load(f)

                    heartbeat_at_str = lease_data.get("heartbeat_at")
                    if not heartbeat_at_str:
                        # No heartbeat, assume stale
                        logger.warning(f"Lease has no heartbeat_at: {lease_path}")
                        leases_expired += 1
                        if not dry_run:
                            lease_path.unlink()
                            leases_deleted += 1
                        continue

                    heartbeat_at = datetime.fromisoformat(heartbeat_at_str)
                    if heartbeat_at.tzinfo is None:
                        heartbeat_at = heartbeat_at.replace(tzinfo=UTC)

                    if heartbeat_at < cutoff_time:
                        worker_id = lease_data.get("worker_id", "unknown")
                        age_minutes = int((now - heartbeat_at).total_seconds() / 60)
                        logger.debug(
                            f"  Expired lease: {lease_path.relative_to(queue_dir)} "
                            f"(worker={worker_id}, age={age_minutes}min)"
                        )
                        leases_expired += 1

                        if not dry_run:
                            try:
                                lease_path.unlink()
                                leases_deleted += 1
                            except Exception as delete_err:
                                logger.error(f"Error deleting lease {lease_path}: {delete_err}")
                                errors += 1

                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing lease.json {lease_path}: {e}")
                    errors += 1
                except Exception as e:
                    logger.error(f"Error processing lease {lease_path}: {e}")
                    errors += 1

    logger.info(
        f"Lease cleanup complete: found={leases_found}, expired={leases_expired}, "
        f"deleted={leases_deleted}, errors={errors}"
    )

    return {
        "leases_found": leases_found,
        "leases_expired": leases_expired,
        "leases_deleted": leases_deleted,
        "errors": errors,
    }


def force_purge_all_leases(
    queue_dir: Path,
    dry_run: bool = False,
) -> dict[str, int]:
    """
    Force remove ALL lease files from a queue directory.

    Use this for testing/reset scenarios where you want to clear the queue
    completely and restart processing.

    Args:
        queue_dir: Root queue directory (e.g., gm-list/pending/)
        dry_run: If True, don't delete files, just count them

    Returns:
        Metrics: {leases_found, leases_deleted, errors}
    """
    leases_found = 0
    leases_deleted = 0
    errors = 0

    if not queue_dir.exists():
        logger.warning(f"Queue directory not found: {queue_dir}")
        return {"leases_found": 0, "leases_deleted": 0, "errors": 0}

    logger.info(f"Force purging ALL leases from {queue_dir}")

    import os

    for root, dirs, files in os.walk(queue_dir):
        for filename in files:
            if filename == "lease.json":
                lease_path = Path(root) / filename
                leases_found += 1

                if not dry_run:
                    try:
                        lease_path.unlink()
                        leases_deleted += 1
                        logger.debug(f"  Deleted: {lease_path.relative_to(queue_dir)}")
                    except Exception as e:
                        logger.error(f"Error deleting lease {lease_path}: {e}")
                        errors += 1

    logger.info(f"Force purge complete: found={leases_found}, deleted={leases_deleted}, errors={errors}")

    return {
        "leases_found": leases_found,
        "leases_deleted": leases_deleted,
        "errors": errors,
    }
