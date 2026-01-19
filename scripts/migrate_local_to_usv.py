import csv
import logging
from cocli.core.website_domain_csv_manager import WebsiteDomainCsvManager
from cocli.models.website_domain_csv import WebsiteDomainCsv
from cocli.core.config import get_cocli_base_dir

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_local_to_usv() -> None:
    base_dir = get_cocli_base_dir() / "indexes"
    manager = WebsiteDomainCsvManager(base_dir)
    
    # 1. Check if we have an old master CSV to import from
    legacy_csv = base_dir / "domains_master.csv"
    if legacy_csv.exists():
        logger.info(f"Importing data from {legacy_csv}")
        with open(legacy_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    # Basic cleanup for CSV-to-Model
                    model_data = {}
                    for k, v in row.items():
                        if k in WebsiteDomainCsv.model_fields:
                            if v and v != "None":
                                if k == "tags":
                                    import ast
                                    try:
                                        model_data[k] = ast.literal_eval(v)
                                    except (ValueError, SyntaxError):
                                        model_data[k] = []
                                elif k == "is_email_provider":
                                    model_data[k] = v.lower() == "true"
                                else:
                                    model_data[k] = v
                    
                    item = WebsiteDomainCsv(**model_data)
                    manager.add_or_update(item)
                except Exception as e:
                    logger.warning(f"Failed to import row {row.get('domain')}: {e}")
    
    # 2. Rebuild the cache
    logger.info("Rebuilding search cache...")
    manager.rebuild_cache()
    logger.info("Local migration to Atomic USV complete.")

if __name__ == "__main__":
    migrate_local_to_usv()
