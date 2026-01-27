from cocli.core.config import get_cocli_base_dir
from cocli.utils.usv_utils import csv_to_usv
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_prospect_indexes() -> None:
    """Migrates all individual prospect CSV files to USV."""
    data_dir = get_cocli_base_dir()
    campaigns_dir = data_dir / "campaigns"
    
    if not campaigns_dir.exists():
        return

    for prospect_index_dir in campaigns_dir.glob("**/indexes/google_maps_prospects"):
        logger.info(f"Checking prospect index: {prospect_index_dir}")
        # Inbox and root
        for path in [prospect_index_dir, prospect_index_dir / "inbox"]:
            if not path.exists():
                continue
            for csv_file in path.glob("*.csv"):
                usv_file = csv_file.with_suffix(".usv")
                try:
                    csv_to_usv(str(csv_file), str(usv_file))
                    csv_file.unlink()
                    logger.debug(f"Migrated {csv_file.name}")
                except Exception as e:
                    logger.error(f"Failed to migrate {csv_file}: {e}")

def migrate_caches() -> None:
    """Migrates cache files to USV."""
    data_dir = get_cocli_base_dir()
    cache_dir = data_dir / "cache"
    
    if not cache_dir.exists():
        return
        
    for csv_file in cache_dir.glob("*.csv"):
        # We'll rename them to .usv
        usv_file = csv_file.with_suffix(".usv")
        try:
            csv_to_usv(str(csv_file), str(usv_file))
            # We DON'T unlink yet because we need to update the code to read .usv
            # Actually, if we update the code first, it might fail to find the file.
            # If we migrate first, the code (still CSV) will fail.
            # Best is to migrate and keep BOTH until code is updated, OR update code to handle both.
            logger.info(f"Migrated cache {csv_file.name} to USV")
        except Exception as e:
            logger.error(f"Failed to migrate cache {csv_file}: {e}")

if __name__ == "__main__":
    logger.info("Starting local CSV to USV migration...")
    migrate_prospect_indexes()
    migrate_caches()
    logger.info("Migration complete.")
