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
from cocli.core.sharding import get_geo_shard

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def migrate_target_tiles(campaign_name: str, execute: bool = False, push: bool = False) -> None:
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        logger.error(f"Campaign {campaign_name} not found.")
        return

    tiles_dir = campaign_dir / "indexes" / "target-tiles"
    if not tiles_dir.exists():
        logger.warning(f"No target-tiles found at {tiles_dir}")
        return

    logger.info(f"--- Sharding Target Tiles Index: {campaign_name} ---")
    
    # 1. Identify tenth-degree folders that are not already in a shard folder
    # A shard folder is a single digit (with optional sign)
    to_move = []
    for item in tiles_dir.iterdir():
        if item.is_dir():
            name = item.name
            # If it looks like a coordinate folder (has a dot)
            if "." in name:
                try:
                    lat = float(name)
                    to_move.append(item)
                except ValueError:
                    pass

    logger.info(f"Found {len(to_move)} folders to migrate into shards.")
    
    if not execute:
        logger.info("DRY RUN: No folders will be moved.")
        for d in to_move[:10]:
            print(f"  [MOVE] {d.name} -> {get_geo_shard(float(d.name))}/{d.name}")
        return

    # 2. Execute Migration
    moved_count = 0
    for d in to_move:
        try:
            lat = float(d.name)
            shard = get_geo_shard(lat)
            shard_dir = tiles_dir / shard
            shard_dir.mkdir(parents=True, exist_ok=True)
            
            target = shard_dir / d.name
            if target.exists():
                # Merge if target exists (shouldn't happen if we're consistent)
                for file in d.iterdir():
                    shutil.move(str(file), str(target / file.name))
                d.rmdir()
            else:
                shutil.move(str(d), str(target))
            moved_count += 1
        except Exception as e:
            logger.error(f"Failed to move {d.name}: {e}")

    logger.info(f"Migration Complete. Moved {moved_count} folders.")

    # 3. Push to S3
    if (moved_count > 0 or push) and execute:
        do_push = push
        if not push and os.isatty(sys.stdin.fileno()):
            confirm = input("Would you like to PUSH-DELETE these changes to S3 now? (y/N): ")
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
                logger.info("S3 Sync Complete.")
            except Exception as e:
                logger.error(f"Failed to sync to S3: {e}")

if __name__ == "__main__":
    from cocli.core.config import get_campaign
    parser = argparse.ArgumentParser(description="Migrate target-tiles to sharded structure.")
    parser.add_argument("campaign", nargs="?", default=get_campaign(), help="Campaign name")
    parser.add_argument("--execute", action="store_true", help="Actually perform migration")
    parser.add_argument("--push", action="store_true", help="Push changes to S3")
    
    args = parser.parse_args()
    migrate_target_tiles(args.campaign, execute=args.execute, push=args.push)
