# POLICY: frictionless-data-policy-enforcement
import logging
import shutil
from cocli.core.paths import paths
from cocli.core.sharding import get_place_id_shard

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("migrate_inbox")

def migrate_campaign_inbox(campaign_name: str) -> None:
    logger.info(f"--- Migrating USV files from inbox to wal for campaign: {campaign_name} ---")
    
    # 1. Source and Destination
    campaign_path = paths.campaign(campaign_name)
    index_dir = campaign_path.path / "indexes" / "google_maps_prospects"
    inbox_dir = index_dir / "inbox"
    wal_dir = index_dir / "wal"
    
    if not inbox_dir.exists():
        logger.info("Inbox directory does not exist. Nothing to migrate.")
        return

    wal_dir.mkdir(parents=True, exist_ok=True)

    total_files = 0
    migrated_files = 0
    errors = 0
    
    # Scan inbox for USV files
    for file_path in inbox_dir.glob("*.usv"):
        total_files += 1
        place_id = file_path.stem
        
        # Calculate correct shard for this place_id
        shard = get_place_id_shard(place_id)
        target_dir = wal_dir / shard
        target_path = target_dir / file_path.name
        
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            
            if target_path.exists():
                # If target exists, we append/merge?
                # For now, let's just overwrite since these are supposed to be atomic results
                # or we can use the _merge_usv logic if we were strictly merging.
                # But these are usually single-item files.
                logger.debug(f"Target exists, overwriting: {target_path.name}")
            
            shutil.move(str(file_path), str(target_path))
            migrated_files += 1
        except Exception as e:
            logger.error(f"Error migrating {file_path.name}: {e}")
            errors += 1

    logger.info("--- Migration Complete ---")
    logger.info(f"Total files found in inbox: {total_files}")
    logger.info(f"Total files migrated to wal: {migrated_files}")
    logger.info(f"Errors: {errors}")
    
    # Remove inbox if empty
    if not any(inbox_dir.iterdir()):
        logger.info("Inbox is empty, removing it.")
        inbox_dir.rmdir()

if __name__ == "__main__":
    import sys
    campaign = sys.argv[1] if len(sys.argv) > 1 else "roadmap"
    migrate_campaign_inbox(campaign)
