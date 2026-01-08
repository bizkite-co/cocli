import json
from cocli.core.config import get_scraped_areas_index_dir

def migrate() -> None:
    source_dir = get_scraped_areas_index_dir()
    target_dir = source_dir.parent / "scraped-tiles"
    
    print(f"Scanning {source_dir} for legacy JSON indices...")
    
    # phrase/latX_lonY/tile_id.json
    json_files = list(source_dir.glob("**/*.json"))
    total = len(json_files)
    print(f"Found {total} files to migrate.")

    migrated_count = 0
    for i, jf in enumerate(json_files):
        if i % 100 == 0:
            print(f"Processing {i}/{total}...")
        try:
            with open(jf, "r") as f:
                data = json.load(f)
            
            tile_id = data.get("tile_id")
            phrase = data.get("phrase")
            scrape_date = data.get("scrape_date")
            items_found = data.get("items_found", 0)

            if not tile_id or not phrase:
                continue

            lat_str, lon_str = tile_id.split("_")
            
            # Destination: scraped-tiles/30.2/-97.7/phrase.csv
            witness_dir = target_dir / lat_str / lon_str
            witness_dir.mkdir(parents=True, exist_ok=True)
            witness_path = witness_dir / f"{phrase}.csv"

            # Skip if already exists
            if witness_path.exists():
                continue

            with open(witness_path, "w") as wf:
                wf.write("scrape_date,items_found\n")
                wf.write(f"{scrape_date},{items_found}\n")
            
            migrated_count += 1
        except Exception as e:
            print(f"Error migrating {jf}: {e}")

    print("\nMigration Complete!")
    print(f"  Files processed: {len(json_files)}")
    print(f"  Witness files created: {migrated_count}")

if __name__ == "__main__":
    migrate()
