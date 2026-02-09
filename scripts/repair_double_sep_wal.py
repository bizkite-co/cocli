import os
import sys
from pathlib import Path
from datetime import datetime, UTC
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ValidationError

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.models.google_maps_prospect import GoogleMapsProspect
from cocli.core.utils import UNIT_SEP

def repair_file(path: Path, execute: bool = False) -> bool:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read().strip("\n")
            
        lines = content.split("\n")
        if len(lines) < 2:
            return False
            
        header = lines[0].split(UNIT_SEP)
        data = lines[1].split(UNIT_SEP)
        
        # We handle any length, but zip them to match header to data
        row_dict = {}
        for h, v in zip(header, data):
            if h: row_dict[h] = v
            
        def to_float(val):
            try: return float(val) if val else None
            except: return None

        # Build clean Prospect
        mapped_data = {
            "place_id": row_dict.get("Place_ID") or row_dict.get("id"),
            "name": row_dict.get("Name"),
            "company_slug": row_dict.get("company_slug"),
            "phone_1": row_dict.get("Phone_1"),
            "website": row_dict.get("Website"),
            "full_address": row_dict.get("Full_Address"),
            "latitude": to_float(row_dict.get("Latitude")),
            "longitude": to_float(row_dict.get("Longitude")),
            "processed_by": row_dict.get("processed_by"),
            "discovery_phrase": row_dict.get("discovery_phrase"),
            "discovery_tile_id": row_dict.get("discovery_tile_id")
        }
        
        # Only proceed if we have the absolute minimums
        if not mapped_data["place_id"] or not mapped_data["name"]:
            return False

        # Instantiate real model (handles defaults and strict validation)
        prospect = GoogleMapsProspect(**{k: v for k, v in mapped_data.items() if v is not None})
        
        if execute:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(prospect.to_usv())
            return True
        return True

    except Exception:
        return False

def main():
    execute = "--execute" in sys.argv
    wal_dir = Path("data/campaigns/roadmap/indexes/google_maps_prospects/wal")
    
    print(f"--- Repairing WAL Files (Execute: {execute}) ---")
    
    total = 0
    success = 0
    failed = 0
    
    for usv_file in wal_dir.rglob("*.usv"):
        total += 1
        if repair_file(usv_file, execute=execute):
            success += 1
        else:
            failed += 1
            
        if total % 1000 == 0:
            print(f"Processed {total}...")

    print(f"\nRepair Complete.")
    print(f"Successfully processed: {success}")
    print(f"Failed/Skipped: {failed}")

if __name__ == "__main__":
    main()