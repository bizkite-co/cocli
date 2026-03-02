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
from cocli.core.constants import UNIT_SEP

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

def is_hollow_usv(usv_path: Path) -> bool:
    """Returns True if the USV file is missing critical data."""
    if not usv_path.exists() or usv_path.suffix != ".usv":
        return False
    try:
        content = usv_path.read_text(encoding="utf-8").strip()
        if not content:
            return True
        rows = content.splitlines()
        hollow_rows = 0
        for row in rows:
            fields = row.split(UNIT_SEP)
            # Schema: 0: pid, 1: slug, 2: name, 3: phone, 4: domain, 5: reviews, 6: rating, 7: address, 8: gmb_url
            reviews = fields[5] if len(fields) > 5 else ""
            rating = fields[6] if len(fields) > 6 else ""
            if not reviews or not rating:
                hollow_rows += 1
        return hollow_rows == len(rows)
    except Exception:
        return True

def cleanup_discovery_results(campaign_name: str, execute: bool = False, push: bool = False, delete_hollow: bool = False) -> None:
    campaign_node = paths.campaign(campaign_name)
    results_dir = campaign_node.path / "queues" / "gm-list" / "completed" / "results"
    
    if not results_dir.exists():
        logger.warning(f"No discovery results found at {results_dir}")
        return

    logger.info(f"--- AGGRESSIVE Discovery Results Cleanup: {campaign_name} ---")
    logger.info(f"Target: {results_dir}")
    
    to_delete: list[Path] = []
    
    # 1. Recursive Scan for EVERYTHING
    for root, dirs, files in os.walk(results_dir, topdown=False):
        # A. Check Files
        for f in files:
            if f == "datapackage.json":
                continue
            file_path = Path(root) / f
            rel_parts = file_path.relative_to(results_dir).parts
            
            # Canonical depth: shard/lat/lon/phrase.usv (4 parts)
            if len(rel_parts) != 4:
                to_delete.append(file_path)
                continue
            
            # Pattern: Underscore in path (e.g. lat_lon combined folders)
            if any("_" in p for p in rel_parts[:-1]):
                to_delete.append(file_path)
                continue

            # Hollow check
            if delete_hollow and is_hollow_usv(file_path):
                to_delete.append(file_path)

        # B. Check Directories (Post-order traversal ensures we catch empty ones)
        for d in dirs:
            dir_path = Path(root) / d
            rel_parts = dir_path.relative_to(results_dir).parts
            
            # Pattern: Redundant/Nested shards (e.g. 3/3/ or 3/3.0/)
            if len(rel_parts) >= 2 and rel_parts[-1] == rel_parts[-2]:
                to_delete.append(dir_path)
                continue
            
            # Pattern: Coordinate precision > 1 decimal
            if "." in d:
                decimal_part = d.split(".")[1]
                if len(decimal_part) > 1:
                    to_delete.append(dir_path)

    logger.info(f"Found {len(to_delete)} items for removal.")
    
    if not execute:
        logger.info("DRY RUN: No files will be deleted.")
        for item in to_delete[:10]:
            logger.info(f"  [JUNK] {item.relative_to(results_dir)}")
        return

    # 2. Execute Deletion
    deleted_count = 0
    for item in to_delete:
        try:
            if not item.exists():
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            deleted_count += 1
        except Exception as e:
            logger.error(f"Failed to delete {item}: {e}")

    # 3. Cleanup empty parent directories
    for root, dirs, _ in os.walk(results_dir, topdown=False):
        for d in dirs:
            dir_path = Path(root) / d
            try:
                if dir_path.exists() and not os.listdir(dir_path):
                    dir_path.rmdir()
            except Exception:
                pass

    # 4. Push to S3 (The "Permanent" Fix)
    if push:
        try:
            from cocli.utils.smart_sync_up import run_smart_sync_up
            config = load_campaign_config(campaign_name)
            aws_config = config.get('aws', {})
            bucket = aws_config.get('data_bucket_name')
            
            logger.info(f"Pushing deletions to S3 bucket: {bucket}")
            run_smart_sync_up(
                target_name="gm-list-results",
                bucket_name=bucket,
                prefix=f"campaigns/{campaign_name}/queues/gm-list/completed/results/",
                local_base=results_dir,
                campaign_name=campaign_name,
                aws_config=aws_config,
                workers=20,
                delete_remote=True
            )
            logger.info("S3 Sanitation Complete.")
        except Exception as e:
            logger.error(f"Failed to sync deletions to S3: {e}")

    logger.info(f"Cleanup Complete. Deleted {deleted_count} items.")

if __name__ == "__main__":
    from cocli.core.config import get_campaign
    parser = argparse.ArgumentParser(description="Aggressive cleanup of non-conforming discovery results.")
    parser.add_argument("campaign", nargs="?", default=get_campaign(), help="Campaign name")
    parser.add_argument("--execute", action="store_true", help="Actually perform the cleanup")
    parser.add_argument("--push", action="store_true", help="Push changes to S3 and delete stale objects")
    parser.add_argument("--hollow", action="store_true", help="Also delete hollow USV files")
    
    args = parser.parse_args()
    cleanup_discovery_results(args.campaign, execute=args.execute, push=args.push, delete_hollow=args.hollow)
