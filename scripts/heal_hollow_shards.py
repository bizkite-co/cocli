import os
from pathlib import Path
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.utils.usv_utils import USVDictReader, USVDictWriter

def heal_shards(data_path: Path) -> None:
    print(f"Healing hollow shards at {data_path}...")
    
    # 1. Load Master Recovery Map
    master_map = {} # place_id -> slug
    master_path = Path("data/campaigns/turboship/recovery/indexes/gm-detail-to-slug/identity-tripod-recovery-master.usv")
    if not master_path.exists():
        print("Master map not found.")
        return
        
    with open(master_path, "r") as f:
        reader = USVDictReader(f)
        for row in reader:
            pid = row.get("place_id")
            slug = row.get("company_slug")
            if pid and slug:
                master_map[pid] = slug
    
    prospect_dir = data_path / "campaigns/turboship/indexes/google_maps_prospects"
    companies_dir = data_path / "companies"
    
    healed_count = 0
    error_count = 0
    
    # 2. Iterate through shards
    for shard in prospect_dir.glob("*.usv"):
        shard_pid = shard.stem
        if shard_pid not in master_map:
            continue
            
        slug = master_map[shard_pid]
        company_index = companies_dir / slug / "_index.md"
        
        if not company_index.exists():
            continue
            
        try:
            # Read company metadata
            from cocli.utils.yaml_utils import resilient_safe_load
            content = company_index.read_text()
            if "---" not in content:
                continue
            yaml_part = content.split("---")[1]
            metadata = resilient_safe_load(yaml_part)
            if not metadata:
                continue
            
            # Create a new prospect object
            # Many companies have full_address instead of street_address
            name = metadata.get("name")
            if not name:
                continue
                
            street = metadata.get("street_address") or metadata.get("full_address")
            zip_code = metadata.get("zip_code")
            
            from cocli.core.text_utils import slugify, calculate_company_hash
            
            prospect = GoogleMapsProspect(
                place_id=shard_pid,
                name=name,
                company_slug=slugify(name),
                company_hash=calculate_company_hash(name, street, zip_code),
                street_address=street,
                city=metadata.get("city"),
                zip=zip_code,
                website=metadata.get("website_url"),
                domain=metadata.get("domain"),
                phone_1=None
            )
            
            # Save the healed shard
            with open(shard, "w") as f:
                writer = USVDictWriter(f, fieldnames=list(prospect.model_dump().keys()))
                writer.writeheader()
                writer.writerow(prospect.model_dump())
            
            healed_count += 1
            if healed_count % 1000 == 0:
                print(f"Healed {healed_count} shards...")
                
        except Exception:
            error_count += 1
            continue

    print("\n--- Healing Report ---")
    print(f"Successfully Healed: {healed_count}")
    print(f"Errors: {error_count}")

if __name__ == "__main__":
    data_home = Path("data")
    if not data_home.exists():
        data_home = Path(os.getenv("COCLI_DATA_HOME", Path.home() / ".local/share/cocli_data"))
    
    heal_shards(data_home)
