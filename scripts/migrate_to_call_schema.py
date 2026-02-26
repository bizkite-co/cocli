# POLICY: frictionless-data-policy-enforcement
import logging
from cocli.core.paths import paths
from cocli.models.campaigns.queues.to_call import ToCallTask
from cocli.core.constants import UNIT_SEP

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("migrate_queue")

def migrate_to_call_queue(campaign_name: str) -> None:
    logger.info(f"--- Migrating To-Call Queue Schema for campaign: {campaign_name} ---")
    
    # 1. Target Directory
    queue_root = paths.campaign(campaign_name).path / "queues" / "to-call"
    
    if not queue_root.exists():
        logger.info(f"Queue root {queue_root} does not exist.")
        return

    migrated_count = 0
    errors = 0
    
    # Scan pending, scheduled, and processing
    for file_path in queue_root.rglob("*.usv"):
        if file_path.name == "datapackage.json":
            continue
            
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().strip("\n")
            
            if not content:
                continue
                
            parts = content.split(UNIT_SEP)
            
            # Legacy Schema detection (starts with UUID like 'dd91d8a6...')
            # Sequence was: [id, schema_version, domain, company_slug, campaign_name, ...]
            # We want: [company_slug, domain, campaign_name, schema_version, ...]
            
            if len(parts) >= 5 and "-" in parts[0] and len(parts[0]) == 36:
                logger.info(f"Migrating legacy file: {file_path.name}")
                
                # Extract known fields
                _old_id = parts[0]
                old_version = parts[1]
                old_domain = parts[2]
                old_slug = parts[3]
                old_campaign = parts[4]
                remaining = parts[5:]
                
                # Construct new data (using the fixed QueueMessage structure)
                # company_slug, domain, campaign_name, schema_version, ...
                new_parts = [old_slug, old_domain, old_campaign, old_version] + remaining
                
                new_content = UNIT_SEP.join(new_parts) + "\n"
                
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                
                migrated_count += 1
            else:
                # Try to load via model to see if it's already conforming
                try:
                    ToCallTask.from_usv(content)
                    logger.debug(f"File {file_path.name} already conforms to schema.")
                except Exception as e:
                    logger.warning(f"File {file_path.name} does not conform and is not legacy: {e}")
                    
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            errors += 1

    logger.info("\n--- Migration Complete ---")
    logger.info(f"Total files migrated: {migrated_count}")
    logger.info(f"Errors: {errors}")

if __name__ == "__main__":
    import sys
    campaign = sys.argv[1] if len(sys.argv) > 1 else "roadmap"
    migrate_to_call_queue(campaign)
