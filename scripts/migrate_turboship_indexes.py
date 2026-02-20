import sys
from pathlib import Path
from typing import Optional
import os

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.models.quarantine.turboship_legacy import TurboshipLegacyProspect

def migrate_record(line: str) -> Optional[GoogleMapsProspect]:
    if not line.strip() or "created_at\x1f" in line: # Skip header
        return None
        
    try:
        # 1. Ingest via Turboship Legacy Model
        legacy = TurboshipLegacyProspect.from_usv_line(line)
        
        # Sanitize newlines in the raw full_address before transformation
        if legacy.full_address:
            legacy.full_address = legacy.full_address.replace("\n", " ").replace("\r", " ")
        
        # 2. Transform to Gold Standard Model
        return legacy.to_ideal()
    except Exception:
        # print(f"Error migrating record: {e}")
        return None

def get_shard(place_id: str) -> str:
    """Standard sharding: last character of place_id."""
    if not place_id:
        return "_"
    return place_id[-1]

def main() -> None:
    campaign = "turboship"
    # Use the established data home
    data_home = Path(os.environ.get("COCLI_DATA_HOME", Path.home() / ".local/share/cocli_data"))
    campaign_dir = data_home / "campaigns" / campaign
    
    legacy_index_dir = campaign_dir / "indexes" / "google_maps_prospects"
    recovery_dir = campaign_dir / "recovery" / "indexes" / "google_maps_prospects"
    wal_dir = recovery_dir / "wal"
    
    recovery_dir.mkdir(parents=True, exist_ok=True)
    wal_dir.mkdir(parents=True, exist_ok=True)
    
    print("--- Turboship Index Migration ---")
    print(f"Source: {legacy_index_dir}")
    print(f"Destination: {wal_dir}")
    
    # Generate metadata in the recovery folder
    GoogleMapsProspect.write_datapackage(campaign, output_dir=recovery_dir)

    success = 0
    total_files = 0
    hydrated = 0
    
    if not legacy_index_dir.exists():
        print(f"Error: Legacy index directory not found at {legacy_index_dir}")
        return

    # Process all .usv files in the legacy index
    for usv_file in legacy_index_dir.glob("*.usv"):
        total_files += 1
        with open(usv_file, 'r', encoding='utf-8') as f:
            # Read entire file and split by Record Separator (\x1e)
            content = f.read()
            # The architectural boundary is the Record Separator
            raw_records = content.split('\x1e')
            
            for raw_record in raw_records:
                if not raw_record.strip():
                    continue
                
                # IMPORTANT: Replace ALL newlines with spaces within the record 
                # BEFORE any other processing. This fixes records that were 
                # incorrectly split into multiple lines.
                sanitized_record = raw_record.replace('\n', ' ').replace('\r', ' ').strip()
                
                # Check for header
                if "created_at\x1f" in sanitized_record:
                    continue
                
                prospect = migrate_record(sanitized_record)
                if prospect:
                    if prospect.street_address and "local-worker" in str(prospect.processed_by):
                        hydrated += 1
                    shard = get_shard(prospect.place_id)
                    shard_dir = wal_dir / shard
                    shard_dir.mkdir(exist_ok=True)
                    
                    out_path = shard_dir / f"{prospect.place_id}.usv"
                    # Write Gold Standard USV (Pydantic to_usv handles escaping)
                    out_path.write_text(prospect.to_usv(), encoding='utf-8')
                    success += 1
                    
        if total_files % 1000 == 0:
            print(f"Processed {total_files} legacy files...")

    print("\nMigration Complete.")
    print(f"Total Unique Records Migrated to WAL: {success}")
    print(f"Records with Structured Addresses: {hydrated}")
    print(f"Recovery index structure created at: {recovery_dir}")

if __name__ == "__main__":
    main()
