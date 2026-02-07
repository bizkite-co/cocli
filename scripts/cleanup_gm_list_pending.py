import os
import sys
import json
import shutil
import logging
import argparse
from pathlib import Path
from datetime import datetime, UTC, timedelta
from typing import Dict, Any

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.core.config import get_campaign_dir
from cocli.core.sharding import get_geo_shard
from cocli.core.text_utils import slugify

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def cleanup_pending_queue(campaign_name: str, dry_run: bool = True):
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        logger.error(f"Campaign {campaign_name} not found.")
        return

    pending_dir = campaign_dir / "queues" / "gm-list" / "pending"
    if not pending_dir.exists():
        logger.warning(f"No pending queue found at {pending_dir}")
        return

    logger.info(f"Cleaning up gm-list pending for {campaign_name} (Dry Run: {dry_run})")
    
    moved = 0
    deleted_leases = 0
    removed_dirs = 0
    now = datetime.now(UTC)

    # 1. Find all lease.json files (the anchor of active work)
    all_leases = list(pending_dir.rglob("lease.json"))
    logger.info(f"Found {len(all_leases)} leases to inspect.")
    
    for lease_path in all_leases:
        try:
            # Path is: pending/{shard}/{lat}/{lon}/{phrase}.[csv|usv]/lease.json
            parts = lease_path.relative_to(pending_dir).parts
            if len(parts) < 4:
                logger.debug(f"Skipping non-standard lease path: {lease_path}")
                continue
            
            # Extract metadata from path
            # parts[-2] is "{phrase}.csv" or "{phrase}.usv"
            # parts[-3] is lon
            # parts[-4] is lat
            phrase_part = parts[-2]
            lon_str = parts[-3]
            lat_str = parts[-4]
            
            try:
                lat = float(lat_str)
                lon = float(lon_str)
            except ValueError:
                logger.warning(f"Invalid coordinate in path: {lease_path}")
                continue
                
            phrase_slug = slugify(phrase_part.replace(".csv", "").replace(".usv", ""))
            
            # Normalize to 1 decimal place
            lat_norm = round(lat, 1)
            lon_norm = round(lon, 1)
            
            # Calculate New Gold Standard Path
            shard = get_geo_shard(lat_norm)
            # Standard: {shard}/{lat}/{lon}/{phrase}.csv/lease.json
            new_lease_dir = pending_dir / shard / f"{lat_norm}" / f"{lon_norm}" / f"{phrase_slug}.csv"
            new_lease_path = new_lease_dir / "lease.json"
            
            # Check if expired
            is_expired = False
            try:
                with open(lease_path, 'r') as f:
                    data = json.load(f)
                
                # Check expires_at or heartbeat_at
                expires_at_str = data.get("expires_at")
                if expires_at_str:
                    expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                    if now > expires_at:
                        is_expired = True
                else:
                    # Fallback: check file mtime (if lease has no expiry info)
                    mtime = datetime.fromtimestamp(lease_path.stat().st_mtime, UTC)
                    if now > (mtime + timedelta(minutes=15)):
                        is_expired = True
            except Exception:
                is_expired = True # If we can't read it, it's junk

            if is_expired:
                logger.info(f"Purging EXPIRED lease: {lease_path.relative_to(pending_dir)}")
                if not dry_run: lease_path.unlink()
                deleted_leases += 1
            else:
                # Active lease: Move to new standard path
                if lease_path.resolve() != new_lease_path.resolve():
                    logger.info(f"Normalizing ACTIVE lease: {lease_path.relative_to(pending_dir)} -> {new_lease_path.relative_to(pending_dir)}")
                    if not dry_run:
                        new_lease_dir.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(lease_path), str(new_lease_path))
                        
                        # Also move task.json if it exists
                        old_task = lease_path.parent / "task.json"
                        if old_task.exists():
                            shutil.move(str(old_task), str(new_lease_dir / "task.json"))
                    moved += 1
                
        except Exception as e:
            logger.error(f"Error processing lease {lease_path}: {e}")

    # 2. Cleanup empty directories
    if not dry_run:
        logger.info("Cleaning up empty directories...")
        for root, dirs, files in os.walk(pending_dir, topdown=False):
            for d in dirs:
                dir_path = Path(root) / d
                try:
                    # Only remove if truly empty (no hidden files)
                    if not any(dir_path.iterdir()):
                        dir_path.rmdir()
                        removed_dirs += 1
                except OSError:
                    pass

    logger.info(f"Done. Active Leases Normalized: {moved}, Expired Leases Purged: {deleted_leases}")
    if not dry_run:
        logger.info(f"Empty directories removed: {removed_dirs}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Normalize gm-list pending queue and purge expired leases.")
    parser.add_argument("campaign", help="Campaign name")
    parser.add_argument("--execute", action="store_true", help="Actually perform the moves and deletes")
    
    args = parser.parse_args()
    cleanup_pending_queue(args.campaign, dry_run=not args.execute)