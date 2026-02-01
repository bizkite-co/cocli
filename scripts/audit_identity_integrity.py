import os
from pathlib import Path
from cocli.utils.usv_utils import USVDictReader
import logging

# Configure logging to be quiet by default
logging.basicConfig(level=logging.ERROR)

def audit_dataset(data_path: Path) -> None:
    print(f"Auditing Identity Integrity at {data_path}...")
    
    # Load Master Recovery Map
    master_map = {} # place_id -> slug
    master_path = Path("data/campaigns/turboship/recovery/indexes/gm-detail-to-slug/identity-tripod-recovery-master.usv")
    if master_path.exists():
        with open(master_path, "r") as f:
            reader = USVDictReader(f)
            for row in reader:
                pid = row.get("place_id")
                slug = row.get("company_slug")
                if pid and slug:
                    master_map[pid] = slug
    print(f"Loaded {len(master_map)} links from master recovery map.")

    stats = {
        "total_shards": 0,
        "conforming (id+hash)": 0,
        "partially_linked (id_only)": 0,
        "dislocated (no_id_in_file)": 0,
        "recoverable_via_master_map": 0,
        "truly_lost (no_id_no_map)": 0,
    }
    
    prospect_dir = data_path / "campaigns/turboship/indexes/google_maps_prospects"
    if not prospect_dir.exists():
        print(f"Prospect index not found at {prospect_dir}")
        return

    recoverable_ids = []

    for shard in prospect_dir.glob("*.usv"):
        stats["total_shards"] += 1
        shard_pid = shard.stem
        
        try:
            with open(shard, "r") as f:
                reader = USVDictReader(f)
                records = list(reader)
                
                # Check if file has any data records
                if not records or shard.stat().st_size < 50:
                    stats["dislocated (no_id_in_file)"] += 1
                    if shard_pid in master_map:
                        stats["recoverable_via_master_map"] += 1
                        recoverable_ids.append((shard_pid, master_map[shard_pid]))
                    else:
                        stats["truly_lost (no_id_no_map)"] += 1
                    continue
                
                for row in records:
                    pid = row.get("place_id") or row.get("Place_ID")
                    has_id = pid and pid != "None" and pid.strip() != ""
                    
                    c_hash = row.get("company_hash") or row.get("Company_Hash")
                    has_hash = c_hash and "-" in str(c_hash)
                    
                    if has_id and has_hash:
                        stats["conforming (id+hash)"] += 1
                    elif has_id:
                        stats["partially_linked (id_only)"] += 1
                    else:
                        stats["dislocated (no_id_in_file)"] += 1
                        if shard_pid in master_map:
                            stats["recoverable_via_master_map"] += 1
                            recoverable_ids.append((shard_pid, master_map[shard_pid]))
                        else:
                            stats["truly_lost (no_id_no_map)"] += 1
                    
        except Exception:
            stats["dislocated (no_id_in_file)"] += 1
            if shard_pid in master_map:
                stats["recoverable_via_master_map"] += 1
                recoverable_ids.append((shard_pid, master_map[shard_pid]))
            else:
                stats["truly_lost (no_id_no_map)"] += 1

    # Save intermediate list
    recovery_dir = Path("data/campaigns/turboship/recovery/indexes/gm-detail-to-slug")
    recovery_dir.mkdir(parents=True, exist_ok=True)
    recoverable_path = recovery_dir / "recoverable_ids.usv"
    with open(recoverable_path, "w") as f:
        f.write("place_id\x1fcompany_slug\x1e\n")
        for pid, slug in recoverable_ids:
            f.write(f"{pid}\x1f{slug}\x1e\n")
    
    print(f"Saved {len(recoverable_ids)} recoverable records to {recoverable_path}")
    print("\n--- Audit Report ---")
    for key, value in stats.items():
        print(f"{key.replace('_', ' ').title()}: {value}")

if __name__ == "__main__":
    data_home = Path("data")
    if not data_home.exists():
        data_home = Path(os.getenv("COCLI_DATA_HOME", Path.home() / ".local/share/cocli_data"))
    audit_dataset(data_home)
