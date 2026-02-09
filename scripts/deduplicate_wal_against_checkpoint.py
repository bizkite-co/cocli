import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.core.utils import UNIT_SEP

def deduplicate_wal(execute: bool = False):
    index_dir = Path("data/campaigns/roadmap/indexes/google_maps_prospects")
    checkpoint_path = index_dir / "prospects.checkpoint.usv"
    wal_dir = index_dir / "wal"

    if not checkpoint_path.exists():
        print(f"Checkpoint not found: {checkpoint_path}")
        return

    print(f"--- Deduplicating WAL against Checkpoint (Execute: {execute}) ---")

    # 1. Load Checkpoint IDs
    checkpoint_pids = set()
    try:
        with open(checkpoint_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                parts = line.split(UNIT_SEP)
                if parts:
                    checkpoint_pids.add(parts[0])
    except Exception as e:
        print(f"Error reading checkpoint: {e}")
        return

    print(f"Loaded {len(checkpoint_pids)} Place IDs from Checkpoint.")

    # 2. Scan WAL
    purged_count = 0
    total_wal = 0
    
    for usv_file in wal_dir.rglob("*.usv"):
        total_wal += 1
        # The filename is the place_id
        pid = usv_file.stem
        
        if pid in checkpoint_pids:
            if execute:
                usv_file.unlink()
            purged_count += 1
        
        if total_wal % 5000 == 0:
            print(f"Scanned {total_wal} WAL files...")

    print("\nScan Complete.")
    print(f"Total WAL files: {total_wal}")
    print(f"Redundant files identified: {purged_count}")
    
    if not execute and purged_count > 0:
        print(f"Run with --execute to delete {purged_count} files.")
    elif execute:
        print(f"Successfully deleted {purged_count} redundant files.")

if __name__ == "__main__":
    execute = "--execute" in sys.argv
    deduplicate_wal(execute=execute)
