import json
import shutil
import logging
import argparse

from cocli.core.paths import paths
from cocli.core.config import get_all_campaign_dirs

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def find_task_campaign(task_id: str, exclude_campaign: str) -> str | None:
    """
    Searches all campaigns (except the exclude one) to find where a task_id belongs.
    Checks pending and completed queues.
    """
    campaign_dirs = get_all_campaign_dirs()
    for c_dir in campaign_dirs:
        campaign_name = c_dir.name
        if campaign_name == exclude_campaign:
            continue
            
        # Check gm-details queue (the most likely source of misrouting)
        # We check both pending and completed
        queue_path = paths.campaign(campaign_name).queue("gm-details").path
        
        # 1. Check pending (sharded)
        if list(queue_path.glob(f"pending/**/{task_id}.json")):
            return campaign_name
            
        # 2. Check completed (sharded)
        if list(queue_path.glob(f"completed/**/{task_id}.json")):
            return campaign_name
            
        # 3. Check results (non-sharded)
        if (queue_path / "completed" / "results" / f"{task_id}.json").exists():
            return campaign_name
            
    return None

def repair_misrouted_results(source_campaign: str, dry_run: bool = True) -> None:
    """
    Scans a campaign's results for gossip-synced items that don't belong there.
    """
    logger.info(f"Starting repair for campaign: {source_campaign} (Dry Run: {dry_run})")
    
    # gm-details is the primary focus as it uses JSON markers for completion
    results_dir = paths.campaign(source_campaign).queue("gm-details").completed / "results"
    
    if not results_dir.exists():
        logger.warning(f"Results directory not found: {results_dir}")
        return

    misrouted_count = 0
    moved_count = 0
    
    for marker_path in results_dir.glob("*.json"):
        try:
            with open(marker_path, "r") as f:
                data = json.load(f)
            
            # We only care about gossip-synced items
            if data.get("synced_via") != "gossip":
                continue
                
            task_id = data.get("id") or marker_path.stem
            
            # Find where it actually belongs
            target_campaign = find_task_campaign(task_id, source_campaign)
            
            if target_campaign:
                misrouted_count += 1
                dest_dir = paths.campaign(target_campaign).queue("gm-details").completed / "results"
                dest_path = dest_dir / marker_path.name
                
                logger.info(f"Found misrouted task {task_id}: {source_campaign} -> {target_campaign}")
                
                if not dry_run:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    if not dest_path.exists():
                        shutil.move(str(marker_path), str(dest_path))
                        moved_count += 1
                        logger.info(f"  MOVED: {marker_path.name}")
                    else:
                        marker_path.unlink()
                        logger.info(f"  DELETED (Duplicate): {marker_path.name}")
            
        except Exception as e:
            logger.error(f"Error processing {marker_path}: {e}")

    logger.info(f"Summary: Found {misrouted_count} misrouted items.")
    if not dry_run:
        logger.info(f"Successfully relocated {moved_count} items.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Repair misrouted gossip results.")
    parser.add_argument("--campaign", default="turboship", help="Source campaign to scan (default: turboship)")
    parser.add_argument("--fix", action="store_true", help="Apply the fixes (default is dry-run)")
    
    args = parser.parse_args()
    repair_misrouted_results(args.campaign, dry_run=not args.fix)
