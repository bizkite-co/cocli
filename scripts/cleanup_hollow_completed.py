#!/usr/bin/env python3
import shutil
import json
import logging

from cocli.core.config import get_campaign, get_campaign_dir

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def cleanup(campaign_name: str) -> None:
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        logger.error(f"Campaign {campaign_name} not found.")
        return

    completed_dir = campaign_dir / "queues" / "gm-details" / "completed"
    recovery_dir = campaign_dir / "recovery" / "completed"
    
    # 1. Ensure recovery dir exists
    recovery_dir.mkdir(parents=True, exist_ok=True)
    
    if not completed_dir.exists():
        logger.warning(f"Completed directory not found: {completed_dir}")
        return

    logger.info(f"Scanning {completed_dir}...")
    all_files = list(completed_dir.glob("*.json"))
    total_found = len(all_files)
    
    hollow_count = 0
    valid_count = 0
    
    for f_path in all_files:
        try:
            with open(f_path, 'r') as f:
                data = json.load(f)
            
            name = data.get("name", "")
            slug = data.get("company_slug", "")
            
            # Criteria for "Hollow": name or slug < 3 chars
            if not name or not slug or len(str(name)) < 3 or len(str(slug)) < 3:
                shutil.move(str(f_path), str(recovery_dir / f_path.name))
                hollow_count += 1
            else:
                valid_count += 1
        except Exception as e:
            logger.error(f"Error processing {f_path}: {e}")

    logger.info("-" * 40)
    logger.info(f"Total processed: {total_found}")
    logger.info(f"Moved to recovery (Hollow): {hollow_count}")
    logger.info(f"Remaining in completed (Valid): {valid_count}")

if __name__ == "__main__":
    from cocli.core.config import get_campaign
    cleanup(get_campaign() or "roadmap")