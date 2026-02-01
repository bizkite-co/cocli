from rich.progress import track
from cocli.core.config import get_cocli_base_dir
from cocli.models.google_maps_prospect import GoogleMapsProspect
from cocli.utils.usv_utils import USVDictReader
from cocli.core.prospects_csv_manager import ProspectsIndexManager

def relink(campaign: str = "turboship"):
    manager = ProspectsIndexManager(campaign)
    
    cache_dir = get_cocli_base_dir() / "cache"
    cache_path = cache_dir / "google_maps_cache.usv"
    if not cache_path.exists():
        print(f"Cache not found: {cache_path}")
        return

    # 1. Load cache into memory (keyed by place_id)
    cache_data = {}
    print(f"Loading cache from {cache_path}...")
    with open(cache_path, 'r', encoding='utf-8') as f:
        reader = USVDictReader(f)
        for row in reader:
            # Handle PascalCase to snake_case mapping via model
            try:
                # Map headers
                mapped_row = {}
                for k, v in row.items():
                    lk = k.lower()
                    if lk == "place_id":
                        mapped_row["place_id"] = v
                    elif lk == "name":
                        mapped_row["name"] = v
                    elif lk == "full_address":
                        mapped_row["full_address"] = v
                    elif lk == "street_address":
                        mapped_row["street_address"] = v
                    elif lk == "city":
                        mapped_row["city"] = v
                    elif lk == "zip":
                        mapped_row["zip"] = v
                    elif lk == "latitude":
                        mapped_row["latitude"] = v
                    elif lk == "longitude":
                        mapped_row["longitude"] = v
                    elif lk == "website":
                        mapped_row["website"] = v
                    elif lk == "domain":
                        mapped_row["domain"] = v
                    elif lk == "phone_1":
                        mapped_row["phone_1"] = v
                    elif lk == "thumbnail_url":
                        mapped_row["thumbnail_url"] = v
                    else:
                        mapped_row[lk] = v
                
                prospect = GoogleMapsProspect.model_validate(mapped_row)
                if prospect.place_id:
                    cache_data[prospect.place_id] = prospect
            except Exception:
                # print(f"Error parsing cache row: {e}")
                continue

    print(f"Loaded {len(cache_data)} prospects from cache.")

    # 2. Iterate through all shards in the campaign and update them if data found in cache
    shards = list(manager.index_dir.glob("*.usv"))
    updated_count = 0
    
    for shard_path in track(shards, description="Relinking shards"):
        place_id_stem = shard_path.stem
        # Some stems might have escaped characters, but mostly they are just the place_id
        # Let's try direct lookup first, then unescape if needed
        prospect = cache_data.get(place_id_stem)
        
        if not prospect:
            # Try finding by looking INSIDE the file for a place_id
            try:
                with open(shard_path, 'r', encoding='utf-8') as f:
                    shard_reader = USVDictReader(f)
                    for row in shard_reader:
                        pid = row.get("place_id")
                        if pid and pid in cache_data:
                            prospect = cache_data[pid]
                            break
            except Exception:
                continue

        if prospect:
            # Update the shard with full data
            manager.append_prospect(prospect)
            updated_count += 1

    print(f"Updated {updated_count} shards with full metadata from cache.")

if __name__ == "__main__":
    relink()
