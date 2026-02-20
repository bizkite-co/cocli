import sys
import json
import shutil
import logging
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.models.campaigns.queues.gm_details import GmItemTask
from cocli.core.config import get_campaign_dir

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def audit_queue(campaign_name: str, execute: bool = False) -> None:
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        logger.error(f"Campaign {campaign_name} not found.")
        return

    completed_dir = campaign_dir / "queues" / "gm-details" / "completed"
    recovery_dir = campaign_dir / "recovery" / "gm-details" / "completed"
    
    if not completed_dir.exists():
        logger.warning(f"No completed queue found at {completed_dir}")
        return

    logger.info(f"Auditing gm-details completion markers for {campaign_name} (Execute: {execute})")
    
    # Pre-cache existing Place IDs for fast lookup
    logger.info("Pre-caching prospect index...")
    existing_pids = set()
    for f_idx in campaign_dir.rglob("google_maps_prospects/**/*.usv"):
        existing_pids.add(f_idx.stem)
    for f_idx in campaign_dir.rglob("google_maps_prospects/**/*.csv"):
        existing_pids.add(f_idx.stem)
    logger.info(f"Cached {len(existing_pids)} prospect IDs.")
    
    stats = {
        "total": 0,
        "valid": 0,
        "invalid_model": 0,
        "missing_index": 0,
        "moved": 0
    }

    all_files = list(completed_dir.glob("*.json"))
    stats["total"] = len(all_files)
    
    for f_path in all_files:
        try:
            with open(f_path, 'r') as f:
                data = json.load(f)
            
            # 1. Validate against Pydantic Model (Name/Slug length check)
            try:
                task = GmItemTask.model_validate(data)
                
                # 2. Cross-check against Cached IDs
                if task.place_id not in existing_pids:
                    stats["missing_index"] += 1
                    is_valid = False
                else:
                    is_valid = True
                    stats["valid"] += 1
                    
            except Exception as ve:
                logger.debug(f"Invalid Model: {f_path.name}: {ve}")
                stats["invalid_model"] += 1
                is_valid = False

            # 3. Action
            if not is_valid:
                if execute:
                    recovery_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(f_path), str(recovery_dir / f_path.name))
                    stats["moved"] += 1
                    
        except Exception as e:
            logger.error(f"Error reading {f_path.name}: {e}")

    logger.info("-" * 40)
    logger.info(f"Total Markers: {stats['total']}")
    logger.info(f"Valid & Indexed: {stats['valid']}")
    logger.info(f"Invalid (Model Fail): {stats['invalid_model']}")
    logger.info(f"Missing Index (Hydration Fail): {stats['missing_index']}")
    
    if execute:
        logger.info(f"Successfully moved {stats['moved']} items to recovery.")
    else:
        logger.info("Dry run complete. Use --execute to move invalid markers.")

if __name__ == "__main__":
    import argparse
    from cocli.core.config import get_campaign
    parser = argparse.ArgumentParser(description="Audit completion markers against models and index.")
    parser.add_argument("campaign", nargs="?", default=get_campaign(), help="Campaign name (defaults to active campaign)")
    parser.add_argument("--execute", action="store_true", help="Actually move invalid markers to recovery")
    
    args = parser.parse_args()
    audit_queue(args.campaign, execute=args.execute)
