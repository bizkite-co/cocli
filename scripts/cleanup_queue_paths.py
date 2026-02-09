import os
import sys
import shutil
import logging
import argparse
import subprocess
import re
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.core.config import get_campaign_dir, load_campaign_config
from cocli.core.sharding import get_geo_shard

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def is_non_conforming(name: str) -> bool:
    """Checks if a name (file or dir) violates precision or flatness rules."""
    # Pattern for > 1 decimal place: a dot followed by 2 or more digits, 
    # but we must ensure it's part of a number, not an extension
    if re.search(r"\d+\.\d{2,}", name):
        return True
        
    # Rule 2: Flat naming (lat_lon_phrase)
    # Check for at least one underscore following a number-like part
    if "_" in name and re.search(r"-?\d+\.?\d*_-?\d+\.?\d*_", name):
        return True
        
    return False

def cleanup_queue(campaign_name: str, queue_rel_path: str, execute: bool = False, push: bool = False):
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        logger.error(f"Campaign {campaign_name} not found.")
        return

    base_dir = campaign_dir / queue_rel_path
    if not base_dir.exists():
        logger.warning(f"Directory not found: {base_dir}")
        return

    success_log_path = Path("cleanup_success.log")
    if execute:
        success_log_path.write_text(f"--- Recursive File/Dir Cleanup Log for {queue_rel_path} ---\n")

    logger.info(f"--- Deep Queue Cleanup: {queue_rel_path} ---")
    
    stale_items = []
    for root, dirs, files in os.walk(base_dir, topdown=False):
        # Collect non-conforming directories
        for d in dirs:
            if is_non_conforming(d):
                stale_items.append(Path(root) / d)
        
        # Collect non-conforming files
        for f in files:
            if is_non_conforming(f):
                stale_items.append(Path(root) / f)

    logger.info(f"Found {len(stale_items)} non-conforming items (files and directories).")
    
    if not execute:
        logger.info("DRY RUN: No items will be removed.")
        for item in stale_items[:20]:
            print(f"  [STALE] {item.relative_to(base_dir)}")
        return

    deleted_count = 0
    merged_count = 0
    
    with open(success_log_path, "a") as log:
        for item in stale_items:
            try:
                if not item.exists():
                    continue

                if item.is_dir():
                    # Directory Logic (Merge & Purge)
                    # Try to parse lat/lon if it's a flat folder
                    if "_" in item.name:
                        parts = item.name.split("_")
                        try:
                            lat = round(float(parts[0]), 1)
                            lon = round(float(parts[1]), 1)
                            phrase = "_".join(parts[2:])
                            shard = get_geo_shard(lat)
                            gold_dir = base_dir / shard / f"{lat}" / f"{lon}" / phrase
                        except (ValueError, IndexError):
                            gold_dir = None
                    else:
                        # Just high precision folder
                        try:
                            val = round(float(item.name), 1)
                            gold_dir = item.parent / f"{val}"
                        except ValueError:
                            gold_dir = None

                    if gold_dir and gold_dir != item:
                        for sub in item.iterdir():
                            if sub.is_file():
                                gold_dir.mkdir(parents=True, exist_ok=True)
                                target = gold_dir / sub.name
                                if not target.exists() or (sub.suffix == ".usv" and target.suffix == ".csv"):
                                    if target.exists():
                                        target.unlink()
                                    shutil.move(str(sub), str(target))
                                    merged_count += 1
                                    log.write(f"MERGED DIR CONTENT: {sub.relative_to(base_dir)}\n")

                    shutil.rmtree(item)
                    deleted_count += 1
                    log.write(f"DELETED DIR: {item.relative_to(base_dir)}\n")
                
                else:
                    # File Logic (Simple Purge - we don't usually merge legacy JSON markers)
                    item.unlink()
                    deleted_count += 1
                    log.write(f"DELETED FILE: {item.relative_to(base_dir)}\n")

            except Exception as e:
                print(f"ERROR processing {item}: {e}")

        # Post-cleanup: Remove empty parents
        for root, dirs, files in os.walk(base_dir, topdown=False):
            for d in dirs:
                dir_path = Path(root) / d
                try:
                    if not any(dir_path.iterdir()):
                        dir_path.rmdir()
                        log.write(f"REMOVED EMPTY PARENT: {dir_path.relative_to(base_dir)}\n")
                except OSError:
                    pass

    logger.info(f"Cleanup Complete. Removed {deleted_count} items, Merged {merged_count} unique files.")

    if (deleted_count > 0 or push) and execute:
        do_push = push
        if not push and os.isatty(sys.stdin.fileno()):
            confirm = input("Would you like to PUSH-DELETE these changes to S3 now? (y/N): ")
            do_push = confirm.lower() == 'y'
            
        if do_push:
            try:
                config = load_campaign_config(campaign_name)
                bucket = config['aws']['data_bucket_name']
                prefix = f"campaigns/{campaign_name}/{queue_rel_path}/"
                
                cmd = [
                    "aws", "s3", "sync", 
                    str(base_dir) + "/", 
                    f"s3://{bucket}/{prefix}", 
                    "--delete"
                ]
                logger.info(f"Executing: {' '.join(cmd)}")
                subprocess.run(cmd, check=True)
                logger.info("S3 Sync Complete.")
            except Exception as e:
                logger.error(f"Failed to sync to S3: {e}")

if __name__ == "__main__":
    from cocli.core.config import get_campaign
    parser = argparse.ArgumentParser(description="Cleanup queue paths (files and dirs) recursively.")
    parser.add_argument("campaign", nargs="?", default=get_campaign(), help="Campaign name")
    parser.add_argument("--queue", default="queues/gm-list", help="Relative path to queue")
    parser.add_argument("--execute", action="store_true", help="Actually perform cleanup")
    parser.add_argument("--push", action="store_true", help="Push changes to S3")
    
    args = parser.parse_args()
    cleanup_queue(args.campaign, args.queue, execute=args.execute, push=args.push)
