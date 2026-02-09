import os
from pathlib import Path

def migrate():
    base_dir = Path("data/campaigns/roadmap/indexes/google_maps_prospects")
    wal_dir = base_dir / "wal"
    wal_dir.mkdir(exist_ok=True)
    
    count = 0
    skipped = 0
    
    # Iterate over files in the root of the index
    for item in base_dir.iterdir():
        if item.is_file() and (item.suffix == ".usv" or item.suffix == ".csv"):
            filename = item.name
            # Place IDs start with ChIJ (4 chars). Index 4 is the first char of the unique ID.
            # But our convention is index 5.
            # Example: ChIJ-1... -> index 5 is '1' (or '-' if we count 0-indexed)
            # Let's verify our convention.
            # ProspectsIndexManager uses: shard = place_id[5]
            
            place_id = item.stem
            if len(place_id) > 5:
                shard = place_id[5]
                target_dir = wal_dir / shard
                target_dir.mkdir(exist_ok=True)
                
                target_path = target_dir / filename
                
                # Use os.rename for atomic move on same filesystem
                os.rename(item, target_path)
                count += 1
            else:
                skipped += 1
                
    print(f"Migrated {count} files to WAL structure.")
    print(f"Skipped {skipped} files.")

if __name__ == "__main__":
    migrate()
