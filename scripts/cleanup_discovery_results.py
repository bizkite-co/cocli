# POLICY: frictionless-data-policy-enforcement
import os
import sys
import shutil
import logging
import argparse
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.core.config import load_campaign_config
from cocli.core.paths import paths

# 1. Setup Logging to File
LOG_FILE = Path(".logs/cleanup_discovery.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='a'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def is_non_conforming(name: str) -> bool:
    """Checks if a directory name looks like a coordinate with > 1 decimal place."""
    try:
        if "." in name:
            parts = name.split(".")
            # If it's a coordinate-like name and has > 1 decimal digit
            if parts[0].replace("-", "").isdigit() and len(parts[1]) > 1:
                return True
    except Exception:
        pass
    return False

def cleanup_discovery_results(campaign_name: str, execute: bool = False, push: bool = False) -> None:
    campaign_node = paths.campaign(campaign_name)
    results_dir = campaign_node.path / "queues" / "gm-list" / "completed" / "results"
    
    config = load_campaign_config(campaign_name)
    aws_config = config.get('aws', {})
    bucket = aws_config.get('data_bucket_name')

    if not results_dir.exists():
        logger.warning(f"No discovery results found at {results_dir}")
        return

    # 0. SYNC DOWN FIRST (Safety Mandate)
    if execute or push:
        try:
            from cocli.commands.smart_sync import run_smart_sync
            logger.info("Pulling latest results from S3 to prevent data loss...")
            run_smart_sync(
                target_name="gm-list-completed",
                bucket_name=bucket,
                prefix=f"campaigns/{campaign_name}/queues/gm-list/completed/results/",
                local_base=results_dir,
                campaign_name=campaign_name,
                aws_config=aws_config,
                workers=20
            )
            logger.info("Sync-Down Complete.")
        except Exception as e:
            logger.error(f"Sync-Down failed: {e}. Aborting cleanup for safety.")
            return

    logger.info(f"--- Recursive Discovery Results Cleanup: {campaign_name} ---")
    logger.info(f"Target: {results_dir}")
    
    # 1. Recursive Scan for non-conforming directories
    non_conforming: list[Path] = []
    # results/{shard}/{lat}/{lon}/
    for root_dir, dirs, files in os.walk(results_dir, topdown=False):
        for d_name in dirs:
            dir_path = Path(root_dir) / d_name
            rel_parts = dir_path.relative_to(results_dir).parts
            
            # Pattern A: Non-conforming name (multi-decimal or underscore)
            if is_non_conforming(d_name) or "_" in d_name:
                non_conforming.append(dir_path)
                continue
                
            # Pattern B: Violates Depth (Standard is 3 dirs deep: shard/lat/lon)
            if len(rel_parts) > 3:
                non_conforming.append(dir_path)
                continue
                
            # Pattern C: Redundant Sharding (e.g., 3/3/ or 3/3.0/)
            # If a directory name is identical to its parent, it's a legacy nesting error
            if len(rel_parts) >= 2 and rel_parts[-1] == rel_parts[-2]:
                non_conforming.append(dir_path)

    logger.info(f"Found {len(non_conforming)} non-conforming directories.")
    
    if not execute:
        logger.info("DRY RUN: No files will be moved or deleted.")
        for d_item in non_conforming[:10]:
            logger.info(f"  [STALE] {d_item.relative_to(results_dir)}")
        if len(non_conforming) > 10:
            logger.info(f"  ... and {len(non_conforming) - 10} more")
        return

    # 2. Process Cleanup
    deleted_count = 0
    merged_count = 0
    
    for stale_dir in non_conforming:
        try:
            # Handle both single coordinate names and underscore-delimited 'lat_lon' names
            name = stale_dir.name
            if "_" in name:
                # If it's a combined folder, we just delete it because 
                # the files inside should have been in the lat/lon structure already
                shutil.rmtree(stale_dir)
                deleted_count += 1
                continue

            val = round(float(name), 1)
            # Ensure it rounds to exactly X.Y format (no .0 if integer)
            # Actually OMAP prefers .1 precision consistently
            gold_name = f"{val:.1f}".rstrip('0').rstrip('.') if val == int(val) else f"{val:.1f}"
            gold_dir: Path = stale_dir.parent / gold_name
            
            if gold_dir != stale_dir:
                # Merge files
                if stale_dir.exists():
                    for file_node in stale_dir.iterdir():
                        if file_node.is_file():
                            gold_dir.mkdir(parents=True, exist_ok=True)
                            target_node = gold_dir / file_node.name
                            
                            # USV Preference
                            if not target_node.exists() or (file_node.suffix == ".usv" and target_node.suffix == ".csv"):
                                if target_node.exists():
                                    target_node.unlink()
                                shutil.copy2(str(file_node), str(target_node))
                                merged_count += 1
            
            # Delete stale
            shutil.rmtree(stale_dir)
            deleted_count += 1
        except Exception as e:
            logger.error(f"Failed to process {stale_dir}: {e}")

    # 3. Push to S3 if requested
    if (deleted_count > 0 or push) and push:
        try:
            from cocli.utils.smart_sync_up import run_smart_sync_up
            config = load_campaign_config(campaign_name)
            aws_config = config.get('aws', {})
            bucket = aws_config.get('data_bucket_name')
            
            # Use smart_sync_up for high-performance multi-threaded sync with delete
            logger.info(f"Performing High-Performance S3 Sync-Up for {campaign_name} results...")
            run_smart_sync_up(
                target_name="gm-list-results",
                bucket_name=bucket,
                prefix=f"campaigns/{campaign_name}/queues/gm-list/completed/results/",
                local_base=results_dir,
                campaign_name=campaign_name,
                aws_config=aws_config,
                workers=20,
                delete_remote=True # This performs the efficient batch deletion
            )
            logger.info("High-Performance S3 Sync-Up Complete.")
        except Exception as e:
            logger.error(f"Failed to sync deletions to S3: {e}")

    logger.info(f"Cleanup Complete. Deleted {deleted_count} directories, Merged {merged_count} files.")

if __name__ == "__main__":
    from cocli.core.config import get_campaign
    parser = argparse.ArgumentParser(description="Cleanup discovery results by merging high-precision folders.")
    parser.add_argument("campaign", nargs="?", default=get_campaign(), help="Campaign name")
    parser.add_argument("--execute", action="store_true", help="Actually perform the cleanup")
    parser.add_argument("--push", action="store_true", help="Push changes to S3 and delete stale objects")
    
    args = parser.parse_args()
    cleanup_discovery_results(args.campaign, execute=args.execute, push=args.push)
