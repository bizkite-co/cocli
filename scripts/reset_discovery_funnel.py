# POLICY: frictionless-data-policy-enforcement
import os
import shutil
import argparse
import logging
from pathlib import Path

# Add project root to path
import sys
sys.path.append(str(Path(__file__).parent.parent))

from cocli.core.config import get_campaign_dir, get_campaign
from cocli.core.paths import paths

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def reset_discovery(campaign_name: str, execute: bool = False) -> None:
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        logger.error(f"Campaign {campaign_name} not found.")
        return

    # 1. Targeted Folders to Purge
    targets = [
        # Active Task Pool (Mission Control)
        paths.campaign(campaign_name).queue("discovery-gen").completed,
        # Pending Queue (Leases/Active Tasks)
        paths.campaign(campaign_name).queue("gm-list").pending,
        # Recent Results (Receipts)
        paths.campaign(campaign_name).queue("gm-list").completed / "results",
        # EXECUTIVE DECISION (2026-03-04): Do NOT purge raw HTML trace files.
        # These are required for debugging parsing/extraction logic and must be preserved.
    ]

    logger.info(f"--- Discovery Funnel Reset: {campaign_name} (Execute: {execute}) ---")
    
    for target in targets:
        if not target.exists():
            logger.info(f"Skipping non-existent: {target}")
            continue
            
        # Count files for logging
        file_count = sum(1 for _ in target.rglob("*") if _.is_file())
        logger.info(f"Found {file_count} files in {target}")
        
        if execute:
            try:
                # We delete the contents but keep the root target dir for OMAP compliance
                for item in target.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                logger.info(f"  [SUCCESS] Purged {target}")
            except Exception as e:
                logger.error(f"  [FAILED] Could not purge {target}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aggressively purges discovery-related pending and result data.")
    parser.add_argument("campaign", nargs="?", default=get_campaign(), help="Campaign name")
    parser.add_argument("--execute", action="store_true", help="Actually perform the deletions")
    
    args = parser.parse_args()
    reset_discovery(args.campaign, execute=args.execute)
