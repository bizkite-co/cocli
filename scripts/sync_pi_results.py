"""
Standalone script to sync gm-list results from Pi workers.

Usage:
    python scripts/sync_pi_results.py --campaign roadmap
    python scripts/sync_pi_results.py --campaign roadmap --force
    python scripts/sync_pi_results.py --campaign roadmap --status
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cocli.core.sync_tracker import SyncTracker
from cocli.application.pi_sync_service import PiSyncService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync gm-list results from Pi workers")
    parser.add_argument("--campaign", default="roadmap", help="Campaign name")
    parser.add_argument(
        "--force", action="store_true", help="Force sync ignoring timestamp"
    )
    parser.add_argument("--status", action="store_true", help="Show sync status only")
    args = parser.parse_args()

    tracker = SyncTracker(args.campaign)
    service = PiSyncService(args.campaign)

    if args.status:
        last_sync = tracker.get_last_sync()
        if last_sync:
            from datetime import datetime, UTC

            age = datetime.now(UTC) - last_sync
            age_minutes = age.total_seconds() / 60
            print(f"Last sync: {last_sync.isoformat()} ({age_minutes:.0f} minutes ago)")
            if tracker.needs_sync():
                print("Sync is STALE (>1 hour)")
            else:
                print("Sync is current")
        else:
            print("Never synced")
        return

    if args.force or tracker.needs_sync():
        logger.info(f"Starting PI sync for campaign: {args.campaign}")
        success = service.sync_all_nodes(blocking=True)
        if success:
            tracker.update_last_sync()
            logger.info("Sync completed successfully")
        else:
            logger.error("Sync completed with errors")
            sys.exit(1)
    else:
        logger.info("Sync not needed (recently synced)")


if __name__ == "__main__":
    main()
