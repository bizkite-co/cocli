import os
import sys
import shutil
import logging
import argparse
import subprocess
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.core.config import get_campaign_dir, load_campaign_config
from cocli.core.reporting import get_boto3_session

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
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

def cleanup_target_tiles(campaign_name: str, execute: bool = False, push: bool = False):
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        logger.error(f"Campaign {campaign_name} not found.")
        return

    tiles_dir = campaign_dir / "indexes" / "target-tiles"
    if not tiles_dir.exists():
        logger.warning(f"No target-tiles found at {tiles_dir}")
        return

    logger.info(f"--- Recursive Target Tiles Cleanup: {campaign_name} ---")
    
    # 1. Recursive Scan for non-conforming directories
    non_conforming = []
    for root, dirs, files in os.walk(tiles_dir, topdown=False):
        for d in dirs:
            if is_non_conforming(d):
                non_conforming.append(Path(root) / d)

    logger.info(f"Found {len(non_conforming)} non-conforming directories at various depths.")
    
    if not execute:
        logger.info("DRY RUN: No files will be moved or deleted.")
        for d in non_conforming[:10]:
            print(f"  [STALE] {d.relative_to(tiles_dir)}")
        if len(non_conforming) > 10:
            print(f"  ... and {len(non_conforming) - 10} more")
        return

    # 2. Process Cleanup
    deleted_count = 0
    merged_count = 0
    
    # We iterate in a way that we handle deepest folders first (already handled by topdown=False in os.walk)
    for stale_dir in non_conforming:
        try:
            val = round(float(stale_dir.name), 1)
            gold_dir = stale_dir.parent / f"{val}"
            
            if gold_dir != stale_dir:
                # Merge logic
                for file in stale_dir.iterdir():
                    if file.is_file():
                        gold_dir.mkdir(parents=True, exist_ok=True)
                        target = gold_dir / file.name
                        # Preference: Keep existing USV over CSV, or Newer over Older
                        if not target.exists() or (file.suffix == ".usv" and target.suffix == ".csv"):
                            if target.exists():
                                target.unlink()
                            shutil.move(str(file), str(target))
                            merged_count += 1
            
            # Delete the stale directory if it still exists (might be empty now)
            if stale_dir.exists():
                shutil.rmtree(stale_dir)
            deleted_count += 1
        except Exception as e:
            logger.error(f"Failed to process {stale_dir}: {e}")

    # Final cleanup of empty parents that might have been left behind
    for root, dirs, files in os.walk(tiles_dir, topdown=False):
        for d in dirs:
            dir_path = Path(root) / d
            try:
                if not any(dir_path.iterdir()):
                    dir_path.rmdir()
            except OSError:
                pass

    logger.info(f"Cleanup Complete. Deleted {deleted_count} directories, Merged {merged_count} unique files.")

    # 3. Push-Delete
    if deleted_count > 0 or push:
        do_push = push
        if not push and os.isatty(sys.stdin.fileno()):
            confirm = input(f"Would you like to PUSH-DELETE these changes to S3 now to prevent regression? (y/N): ")
            do_push = confirm.lower() == 'y'
            
        if do_push:
            try:
                config = load_campaign_config(campaign_name)
                bucket = config['aws']['data_bucket_name']
                prefix = f"campaigns/{campaign_name}/indexes/target-tiles/"
                
                cmd = [
                    "aws", "s3", "sync", 
                    str(tiles_dir) + "/", 
                    f"s3://{bucket}/{prefix}", 
                    "--delete"
                ]
                logger.info(f"Executing: {' '.join(cmd)}")
                subprocess.run(cmd, check=True)
                logger.info("S3 Sync Complete (with --delete).")
            except Exception as e:
                logger.error(f"Failed to sync to S3: {e}")

if __name__ == "__main__":
    from cocli.core.config import get_campaign
    parser = argparse.ArgumentParser(description="Cleanup target-tiles recursively by merging high-precision folders.")
    parser.add_argument("campaign", nargs="?", default=get_campaign(), help="Campaign name")
    parser.add_argument("--execute", action="store_true", help="Actually perform the cleanup")
    parser.add_argument("--push", action="store_true", help="Push changes to S3 and delete stale objects there")
    
    args = parser.parse_args()
    cleanup_target_tiles(args.campaign, execute=args.execute, push=args.push)