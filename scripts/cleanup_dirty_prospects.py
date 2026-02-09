import sys
from pathlib import Path
import logging
import pydantic

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.models.google_maps_prospect import GoogleMapsProspect
from cocli.core.sharding import get_place_id_shard
from cocli.core.config import get_campaign_dir
from cocli.utils.usv_utils import USVDictReader

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def migrate_dirty_files(campaign_name: str) -> None:
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        logger.error(f"Campaign {campaign_name} not found.")
        return
        
    prospect_dir = campaign_dir / "indexes" / "google_maps_prospects"
    wal_dir = prospect_dir / "wal"
    inbox_dir = prospect_dir / "inbox"
    
    # 1. Find all dirty files
    # Dirty = files in root or inbox that are not 'wal' or 'recovery' or '.checkpoint.usv'
    dirty_files = []
    
    # Check root
    for p in prospect_dir.glob("*.usv"):
        if p.name != "prospects.checkpoint.usv" and p.name != "validation_errors.usv":
            dirty_files.append(p)
            
    # Check inbox
    if inbox_dir.exists():
        dirty_files.extend(list(inbox_dir.rglob("*.usv")))
        dirty_files.extend(list(inbox_dir.rglob("*.csv")))

    logger.info(f"Found {len(dirty_files)} dirty files to migrate.")
    
    count = 0
    errors = 0
    skipped = 0
    
    for file_path in dirty_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                # Use USVDictReader to handle header detection
                if file_path.suffix == ".usv":
                    first_line = f.readline()
                    f.seek(0)
                    if "created_at" in first_line or "place_id" in first_line:
                        reader = USVDictReader(f)
                    else:
                        # Headerless: map to model fields
                        ordered_fields = ["place_id", "company_slug", "name", "phone_1"]
                        all_fields = list(GoogleMapsProspect.model_fields.keys())
                        remaining = [f for f in all_fields if f not in ordered_fields]
                        fieldnames = ordered_fields + remaining
                        reader = USVDictReader(f, fieldnames=fieldnames)
                else:
                    import csv
                    reader = csv.DictReader(f)

                for row in reader:
                    # Normalize keys
                    normalized_row = {}
                    for k, v in row.items():
                        if not k:
                            continue
                        key = k.lower().replace(" ", "_")
                        if key == "place_id":
                            key = "place_id"
                        if key == "id" and not normalized_row.get("place_id"):
                            key = "place_id"
                        normalized_row[key] = v

                    model_data = {k: v for k, v in normalized_row.items() if k in GoogleMapsProspect.model_fields}
                    
                    try:
                        prospect = GoogleMapsProspect.model_validate(model_data)
                        
                        # Sharding & Write to WAL
                        shard = get_place_id_shard(prospect.place_id)
                        target_dir = wal_dir / shard
                        target_dir.mkdir(parents=True, exist_ok=True)
                        target_path = target_dir / f"{prospect.place_id}.usv"
                        
                        # Write headerless
                        with open(target_path, 'w', encoding='utf-8') as tf:
                            tf.write(prospect.to_usv())
                            
                        count += 1
                        if count % 500 == 0:
                            logger.info(f"Progress: {count} migrated...")
                            
                    except pydantic.ValidationError as ve:
                        logger.warning(f"Validation error in {file_path.name}: {ve}")
                        skipped += 1
                        continue

            # Remove original dirty file after successful processing
            file_path.unlink()
            
        except Exception as e:
            logger.error(f"FAIL processing {file_path}: {e}")
            errors += 1

    logger.info(f"Migration complete. Migrated: {count}, Errors: {errors}, Skipped: {skipped}")

if __name__ == "__main__":
    import argparse
    from cocli.core.config import get_campaign
    parser = argparse.ArgumentParser(description="Migrate dirty root-level prospects to sharded WAL.")
    parser.add_argument("campaign", nargs="?", default=get_campaign(), help="Campaign name")
    args = parser.parse_args()
    migrate_dirty_files(args.campaign)
