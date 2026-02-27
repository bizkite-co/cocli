import os
import sys
import json
import re
from pathlib import Path
from datetime import datetime, timedelta, timezone
import logging
from typing import List

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.core.paths import paths

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("queue_cleanup")

def identify_stale_files(campaign: str, queue_name: str, stale_hours: int = 4) -> List[str]:
    """
    Identifies stale pending tasks and leases in the given queue.
    """
    stale_list = []
    queue_root = paths.queue(campaign, queue_name).pending
    
    if not queue_root.exists():
        logger.warning(f"Queue root not found: {queue_root}")
        return []

    now = datetime.now(timezone.utc)
    stale_threshold = now - timedelta(hours=stale_hours)

    for root, dirs, files in os.walk(queue_root):
        # Check for Path Precision Violations in directories (OMAP Violation)
        for d in dirs:
            dir_path = Path(root) / d
            if re.search(r"\d+\.\d{4,}", d):
                stale_list.append(str(dir_path))
                dirs.remove(d)

        for file in files:
            file_path = Path(root) / file
            
            if file == "lease.json":
                try:
                    with open(file_path, "r") as f:
                        data = json.load(f)
                        expires_at_str = data.get("expires_at")
                        if expires_at_str:
                            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                            if expires_at < now:
                                stale_list.append(str(file_path))
                except Exception:
                    stale_list.append(str(file_path))

            rel_path = file_path.relative_to(queue_root)
            parts = rel_path.parts
            
            max_parts = 3 if queue_name == "gm-details" else 4
            if len(parts) > max_parts:
                stale_list.append(str(file_path))
                continue
            
            if file == "task.json" or file.endswith(".csv") or file.endswith(".usv"):
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
                if mtime < stale_threshold:
                    stale_list.append(str(file_path))

    return stale_list

def generate_cleanup_report(campaign: str, files: List[str]) -> Path:
    report_name = f"cleanup_{campaign}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    report_path = Path("temp") / report_name
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        for item in files:
            f.write(str(item) + "\n")
    logger.info(f"Cleanup report generated with {len(files)} items: {report_path}")
    return report_path

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Audit and identify stale queue items.")
    parser.add_argument("--campaign", default="roadmap")
    parser.add_argument("--queue", default="gm-details", help="Queue name to audit (gm-details, gm-list, etc)")
    parser.add_argument("--hours", type=int, default=4, help="Stale threshold in hours")
    args = parser.parse_args()

    logger.info(f"--- Auditing {args.queue} pending queue for {args.campaign} (Threshold: {args.hours}h) ---")
    stale_files = identify_stale_files(args.campaign, args.queue, args.hours)
    
    if stale_files:
        generate_cleanup_report(args.campaign, stale_files)
    else:
        logger.info("No stale files identified.")
