import sys
from pathlib import Path
import logging
import argparse
from datetime import datetime, UTC
import pydantic

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.models.google_maps_prospect import GoogleMapsProspect
from cocli.core.utils import UNIT_SEP
from cocli.core.sharding import get_place_id_shard
from cocli.core.config import get_campaign_dir

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

REC_SEP = "\x1e"

def migrate_from_plan(campaign_name: str, plan_path: Path) -> None:
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        logger.error(f"Campaign {campaign_name} not found.")
        return
        
    prospect_dir = campaign_dir / "indexes" / "google_maps_prospects"
    audit_log_path = campaign_dir / "migration_audit.log"
    hollow_log_path = campaign_dir / "hollow_prospects.log"
    
    with open(plan_path, 'r') as f:
        file_paths = [Path(line.strip()) for line in f if line.strip()]

    logger.info(f"Executing migration plan: {len(file_paths)} files.")
    
    count = 0
    errors = 0
    skipped = 0
    
    try:
        with open(audit_log_path, 'a') as af, open(hollow_log_path, 'a') as hf:
            for file_path in file_paths:
                if not file_path.exists():
                    logger.warning(f"File not found (already moved?): {file_path.name}")
                    continue
                    
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    if not content:
                        continue
                    
                    # Robust Parsing
                    if REC_SEP in content:
                        records = [r.strip() for r in content.split(REC_SEP) if r.strip()]
                    else:
                        if content.startswith("created_at") or "place_id" in content.split("\n")[0]:
                            records = [r.strip() for r in content.split("\n", 1) if r.strip()]
                        else:
                            records = [content.strip()]

                    if not records:
                        continue

                    if records[0].startswith("created_at") or "place_id" in records[0]:
                        header = [h.strip() for h in records[0].split(UNIT_SEP)]
                        data_body = records[1].replace("\n", "<br>").replace("\r", "<br>") if len(records) > 1 else ""
                        parts = [p.strip() for p in data_body.split(UNIT_SEP)]
                        raw_data = dict(zip(header, parts))
                    else:
                        data_body = records[0].replace("\n", "<br>").replace("\r", "<br>")
                        parts = [p.strip() for p in data_body.split(UNIT_SEP)]
                        fields = list(GoogleMapsProspect.model_fields.keys())
                        raw_data = dict(zip(fields, parts))

                    pid = raw_data.get("place_id") or raw_data.get("Place_ID") or raw_data.get("id") or file_path.stem
                    raw_data["place_id"] = pid

                    # Model Validation
                    try:
                        prospect = GoogleMapsProspect.model_validate(raw_data)
                    except pydantic.ValidationError as ve:
                        name = raw_data.get("name") or raw_data.get("Name") or ""
                        if len(str(name)) < 3:
                            hf.write(f"{datetime.now(UTC).isoformat()} | {pid}\n")
                            skipped += 1
                            # Move hollow to a dedicated folder instead of unlinking immediately?
                            # For now we just skip.
                            continue
                        else:
                            raise ve

                    # Sharding & Write
                    shard = get_place_id_shard(prospect.place_id)
                    new_dir = prospect_dir / shard
                    new_dir.mkdir(parents=True, exist_ok=True)
                    new_path = new_dir / f"{prospect.place_id}.usv"
                    
                    content_usv = prospect.to_usv()
                    with open(new_path, 'w', encoding='utf-8') as f:
                        f.write(content_usv)
                    
                    if new_path.exists() and new_path.stat().st_size > 0:
                        file_path.unlink()
                        count += 1
                        af.write(f"{datetime.now(UTC).isoformat()} | {prospect.place_id}\n")
                        if count % 100 == 0:
                            logger.info(f"Progress: {count} migrated...")
                    else:
                        raise IOError("Verification failed")
                        
                except Exception as e:
                    logger.error(f"FAIL: {file_path.name}: {e}")
                    errors += 1
    except KeyboardInterrupt:
        logger.info("Migration paused by user.")

    logger.info(f"Batch complete. Migrated: {count}, Errors: {errors}, Skipped (Hollow): {skipped}")

if __name__ == "__main__":
    from cocli.core.config import get_campaign
    parser = argparse.ArgumentParser(description="Migrate prospect index from a plan file.")
    parser.add_argument("campaign", nargs="?", default=get_campaign(), help="Campaign name")
    parser.add_argument("plan", help="Path to migration plan text file")
    
    args = parser.parse_args()
    migrate_from_plan(args.campaign, Path(args.plan))