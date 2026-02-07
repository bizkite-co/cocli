import os
import sys
import logging
import argparse
from pathlib import Path
from typing import List

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.core.config import get_campaign, get_campaign_dir
from cocli.core.prospects_csv_manager import ProspectsIndexManager
from cocli.models.google_maps_prospect import GoogleMapsProspect

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def compact_index(campaign_name: str, archive: bool = False) -> None:
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        logger.error(f"Campaign {campaign_name} not found.")
        return

    manager = ProspectsIndexManager(campaign_name)
    checkpoint_path = manager._get_checkpoint_path()
    
    logger.info(f"Starting compaction for {campaign_name}...")
    
    # 1. Collect all prospects (using existing read_all logic which handles duplicates)
    all_prospects: List[GoogleMapsProspect] = list(manager.read_all_prospects())
    logger.info(f"Loaded {len(all_prospects)} unique prospects.")
    
    # 2. Sort by Place ID for consistent ordering and binary search readiness
    all_prospects.sort(key=lambda p: p.place_id or "")
    
    # 3. Write to temporary checkpoint
    temp_checkpoint = checkpoint_path.with_suffix(".tmp")
    count = 0
    with open(temp_checkpoint, 'w', encoding='utf-8') as f:
        for p in all_prospects:
            f.write(p.to_usv())
            count += 1
            if count % 1000 == 0:
                logger.info(f"Written {count} records...")

    # 4. Atomic Swap
    os.replace(temp_checkpoint, checkpoint_path)
    logger.info(f"Checkpoint created: {checkpoint_path} ({checkpoint_path.stat().st_size / 1024 / 1024:.2f} MB)")

    # 5. Optional Archive (Move hot files to an archive folder)
    if archive:
        archive_dir = manager.index_dir / "archive" / datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Archiving hot-layer files to {archive_dir}...")
        
        # We only archive files that are IN the shards (the WAL)
        # Note: This list logic should be careful not to delete the checkpoint itself!
        for shard_dir in manager.index_dir.iterdir():
            if shard_dir.is_dir() and len(shard_dir.name) == 1:
                # Move entire shard dir to archive
                import shutil
                shutil.move(str(shard_dir), str(archive_dir / shard_dir.name))
        
        logger.info("Archive complete. Future writes will re-create shards.")

if __name__ == "__main__":
    from datetime import datetime
    parser = argparse.ArgumentParser(description="Compact sharded prospects into a sorted checkpoint USV.")
    parser.add_argument("campaign", nargs="?", default=get_campaign(), help="Campaign name")
    parser.add_argument("--archive", action="store_true", help="Move compacted hot-layer files to an archive folder")
    
    args = parser.parse_args()
    compact_index(args.campaign, archive=args.archive)
