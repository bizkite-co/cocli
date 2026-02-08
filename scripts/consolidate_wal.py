import os
import shutil
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def consolidate():
    base_dir = Path("data/campaigns/roadmap/indexes/google_maps_prospects")
    target_wal_dir = base_dir / "wal"
    target_wal_dir.mkdir(exist_ok=True)

    # Dictionary to track the "Winner" for each place_id
    # winners[place_id] = { 'path': Path, 'ext': '.usv', 'mtime': float }
    winners = {}
    all_files = []

    # 1. Collect all files from all subdirectories
    logger.info("Scanning for all files...")
    for root, dirs, files in os.walk(base_dir):
        # We want to process everything, including existing wal/ files
        root_path = Path(root)
        for f in files:
            if f.endswith(".usv") or f.endswith(".csv"):
                all_files.append(root_path / f)

    logger.info(f"Found {len(all_files)} total files. Determining winners...")

    # 2. Determine winners based on rules:
    # - USV beats CSV
    # - Newest mtime beats older
    for file_path in all_files:
        place_id = file_path.stem
        mtime = file_path.stat().st_mtime
        ext = file_path.suffix.lower()

        if place_id not in winners:
            winners[place_id] = {'path': file_path, 'ext': ext, 'mtime': mtime}
            continue

        existing = winners[place_id]
        
        # Rule: USV beats CSV
        if ext == ".usv" and existing['ext'] == ".csv":
            winners[place_id] = {'path': file_path, 'ext': ext, 'mtime': mtime}
        # Rule: Same extension, Newest wins
        elif ext == existing['ext'] and mtime > existing['mtime']:
            winners[place_id] = {'path': file_path, 'ext': ext, 'mtime': mtime}
        # Otherwise, existing wins

    logger.info(f"Identified {len(winners)} unique winners. Starting consolidation...")

    # 3. Physically move winners and delete everything else
    processed_count = 0
    for place_id, winner in winners.items():
        if len(place_id) < 6:
            continue
            
        shard = place_id[5]
        shard_dir = target_wal_dir / shard
        shard_dir.mkdir(exist_ok=True)
        
        target_path = shard_dir / f"{place_id}{winner['ext']}"
        
        # If the winner is already at the target path, skip the move
        if winner['path'].resolve() != target_path.resolve():
            # Use copy2 to preserve metadata, then we'll clean up all sources later
            shutil.copy2(winner['path'], target_path)
        
        processed_count += 1
        if processed_count % 5000 == 0:
            logger.info(f"Processed {processed_count} winners...")

    # 4. Cleanup: Delete all source files EXCEPT those in the new wal/ structure
    logger.info("Cleaning up source files and empty directories...")
    
    # We'll just delete the root level shards and inbox, and re-create a clean wal
    # To be extremely safe, we'll delete files we know we processed or that are losers
    for f in all_files:
        # Resolve path to handle symlinks correctly if any
        resolved_f = f.resolve()
        # Keep it if it's inside the new wal structure AND it's a winner
        is_winner_at_target = False
        place_id = f.stem
        if place_id in winners:
            shard = place_id[5]
            expected_target = (target_wal_dir / shard / f"{place_id}{winners[place_id]['ext']}").resolve()
            if resolved_f == expected_target:
                is_winner_at_target = True
        
        if not is_winner_at_target:
            try:
                os.remove(f)
            except Exception as e:
                logger.warning(f"Failed to delete {f}: {e}")

    # 5. Remove empty directories
    for root, dirs, files in os.walk(base_dir, topdown=False):
        if root == str(base_dir) or root == str(target_wal_dir):
            continue
        try:
            os.rmdir(root)
        except OSError:
            pass # Directory not empty

    logger.info("Consolidation complete!")
    logger.info(f"Final unique records in WAL: {len(winners)}")

if __name__ == "__main__":
    consolidate()
