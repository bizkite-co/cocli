import sys
from pathlib import Path
from typing import Optional, Any
from pydantic import ValidationError

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.core.utils import UNIT_SEP

def repair_file(path: Path, execute: bool = False) -> bool:
    print(f"\n--- Debugging: {path.name} ---")
    try:
        with open(path, 'rb') as f:
            raw_content = f.read().decode('utf-8', errors='ignore')
            
        # Normalize all separator variations to \n
        content = raw_content.replace("\x1e\n", "\n").replace("\x1e", "\n")
        while "\n\n" in content:
            content = content.replace("\n\n", "\n")
            
        lines = [line for line in content.split("\n") if line.strip()]
        print(f"  Line count: {len(lines)}")
        if len(lines) < 2:
            print("  FAILED: Less than 2 lines found.")
            return False
            
        header = lines[0].split(UNIT_SEP)
        data = lines[1].split(UNIT_SEP)
        
        print(f"  Header cols: {len(header)}")
        print(f"  Data cols: {len(data)}")
        
        # Strip whitespace
        header = [h.strip() for h in header]
        data = [v.strip() for v in data]
        
        row_dict = {}
        for h, v in zip(header, data):
            if h:
                row_dict[h] = v
            
        print(f"  Sample keys: {list(row_dict.keys())[:10]}")

        def to_float(val: str) -> Optional[float]:
            try:
                return float(val) if val else None
            except Exception:
                return None

        mapped_data: dict[str, Any] = {
            "place_id": row_dict.get("Place_ID") or row_dict.get("place_id") or row_dict.get("id"),
            "name": row_dict.get("Name") or row_dict.get("name"),
            "company_slug": row_dict.get("company_slug"),
            "phone_1": row_dict.get("Phone_1") or row_dict.get("phone_1"),
            "website": row_dict.get("Website") or row_dict.get("website"),
            "full_address": row_dict.get("Full_Address") or row_dict.get("full_address"),
            "latitude": to_float(str(row_dict.get("Latitude") or row_dict.get("latitude") or "")),
            "longitude": to_float(str(row_dict.get("Longitude") or row_dict.get("longitude") or "")),
            "processed_by": row_dict.get("processed_by"),
            "discovery_phrase": row_dict.get("discovery_phrase"),
            "discovery_tile_id": row_dict.get("discovery_tile_id")
        }
        
        print(f"  Mapped PID: {mapped_data['place_id']}")
        print(f"  Mapped Name: {mapped_data['name']}")
        
        if not mapped_data["place_id"] or not mapped_data["name"]:
            print("  FAILED: Missing required identity fields.")
            return False

        # Instantiate real model
        try:
            prospect = GoogleMapsProspect(**{k: v for k, v in mapped_data.items() if v is not None})
            print("  SUCCESS: Model instantiated.")
        except ValidationError as ve:
            print(f"  FAILED: Pydantic Validation Error: {ve}")
            return False
        
        if execute:
            with open(path, 'wb') as bf:
                bf.write(prospect.to_usv().encode('utf-8'))
            print("  SUCCESS: File overwritten.")
            return True
        return True

    except Exception as e:
        print(f"  ERROR: {e}")
        return False

def main() -> None:
    execute = "--execute" in sys.argv
    broken_log = Path("broken_wal_files.log")
    if not broken_log.exists():
        print("Run audit first.")
        return
        
    with open(broken_log, 'r') as f:
        file_paths = [Path(line.split(": ")[0]) for line in f if line.startswith("data/campaigns")]

    print(f"--- Repairing 10 WAL Files (Execute: {execute}) ---")
    
    success = 0
    failed = 0
    
    for usv_file in file_paths[:10]: # ONLY 10 FILES
        if not usv_file.exists():
            continue
        if repair_file(usv_file, execute=execute):
            success += 1
        else:
            failed += 1

    print("\nDebug Complete.")
    print(f"Successfully processed: {success}")
    print(f"Failed/Skipped: {failed}")

if __name__ == "__main__":
    main()