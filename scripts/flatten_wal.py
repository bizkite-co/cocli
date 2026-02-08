import os
import shutil
from pathlib import Path

def flatten():
    base_dir = Path("data/campaigns/roadmap/indexes/google_maps_prospects")
    wal_dir = base_dir / "wal"
    
    if not wal_dir.exists():
        print("WAL directory does not exist. Nothing to flatten.")
        return

    count = 0
    
    # Iterate over all subdirectories in wal/
    for shard_dir in wal_dir.iterdir():
        if shard_dir.is_dir():
            for item in shard_dir.iterdir():
                if item.is_file():
                    target_path = base_dir / item.name
                    # Using os.replace for idempotency/overwriting if necessary
                    os.replace(item, target_path)
                    count += 1
            # Remove shard dir if empty
            try:
                shard_dir.rmdir()
            except OSError:
                pass

    print(f"Flattened {count} files back to root.")

if __name__ == "__main__":
    flatten()
