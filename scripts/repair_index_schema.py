import sys
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.models.google_maps_prospect import GoogleMapsProspect
from cocli.models.quarantine.legacy_prospect import LegacyProspectUSV

def repair_record(line: str) -> Optional[GoogleMapsProspect]:
    if not line.strip():
        return None
        
    try:
        # 1. Ingest via Quarantined Legacy Model
        legacy = LegacyProspectUSV.from_usv_line(line)
        
        # 2. Transform to Gold Standard Model
        return legacy.to_ideal()
    except Exception:
        return None

def main() -> None:
    campaign = "roadmap"
    output_dir_path = "data/campaigns/roadmap/recovery/indexes/google_maps_prospects/"
    
    if "--output-dir" in sys.argv:
        idx = sys.argv.index("--output-dir")
        output_dir_path = sys.argv[idx + 1]
    
    output_dir = Path(output_dir_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate metadata in the recovery folder for validation
    GoogleMapsProspect.write_datapackage(campaign, output_dir=output_dir)

    wal_dir = Path(f"data/campaigns/{campaign}/indexes/google_maps_prospects/wal")
    checkpoint = Path(f"data/campaigns/{campaign}/indexes/google_maps_prospects/prospects.checkpoint.usv")
    
    print(f"--- Index Recovery for {campaign} ---")
    print(f"Destination: {output_dir}")
    
    success = 0
    total_wal = 0
    
    # 1. Process WAL
    if wal_dir.exists():
        print("Scanning WAL shards...")
        for usv_file in wal_dir.rglob("*.usv"):
            if usv_file.name == "validation_errors.usv":
                continue
            total_wal += 1
            content = usv_file.read_text(encoding='utf-8').strip()
            prospect = repair_record(content)
            if prospect:
                out_path = output_dir / f"{prospect.place_id}.usv"
                out_path.write_text(prospect.to_usv(), encoding='utf-8')
                success += 1
            if total_wal % 1000 == 0:
                print(f"Processed {total_wal} WAL files...")

    # 2. Process Checkpoint
    total_checkpoint = 0
    if checkpoint.exists():
        print("Scanning Checkpoint lines...")
        with open(checkpoint, 'r', encoding='utf-8') as f:
            for line in f:
                total_checkpoint += 1
                prospect = repair_record(line.strip())
                if prospect:
                    out_path = output_dir / f"{prospect.place_id}.usv"
                    # Only write if it doesn't exist (WAL wins)
                    if not out_path.exists():
                        out_path.write_text(prospect.to_usv(), encoding='utf-8')
                        success += 1
                if total_checkpoint % 5000 == 0:
                    print(f"Processed {total_checkpoint} checkpoint lines...")

    print("\nRecovery Complete.")
    print(f"Total Unique Records Recovered: {success}")

if __name__ == "__main__":
    main()
