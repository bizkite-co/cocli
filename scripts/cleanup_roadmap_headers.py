# POLICY: frictionless-data-policy-enforcement
import logging
from cocli.core.paths import paths

# Setup logging according to the new standard
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("cleanup_headers")

def cleanup_campaign_headers(campaign_name: str) -> None:
    logger.info(f"--- Cleaning up USV headers for campaign: {campaign_name} ---")
    
    # 1. Target Directories
    campaign_path = paths.campaign(campaign_name)
    prospect_index = campaign_path.path / "indexes" / "google_maps_prospects"
    
    targets = [
        prospect_index / "inbox",
        prospect_index / "wal"
    ]
    
    # Also check 'scraped-tiles' witness index
    witness_dir = campaign_path.path / "indexes" / "scraped-tiles"
    if witness_dir.exists():
        targets.append(witness_dir)

    total_files = 0
    cleaned_files = 0
    
    for target_dir in targets:
        if not target_dir.exists():
            continue
            
        logger.info(f"Scanning {target_dir}...")
        
        # rglob to catch sharded subdirectories
        for file_path in target_dir.rglob("*.usv"):
            total_files += 1
            
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                if not lines:
                    continue
                    
                # Check for headers in the first line
                # "created_at" is in GoogleMapsProspect header
                # "scrape_date" is in ScrapeIndex witness header
                first_line = lines[0]
                if "created_at" in first_line or "scrape_date" in first_line:
                    logger.info(f"Removing header from: {file_path.relative_to(prospect_index.parent)}")
                    
                    # Strip the first line (header)
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.writelines(lines[1:])
                    
                    cleaned_files += 1
            except Exception as e:
                logger.error(f"Error processing {file_path}: {e}")

    logger.info("--- Cleanup Complete ---")
    logger.info(f"Total files scanned: {total_files}")
    logger.info(f"Total files cleaned: {cleaned_files}")

if __name__ == "__main__":
    import sys
    campaign = sys.argv[1] if len(sys.argv) > 1 else "roadmap"
    cleanup_campaign_headers(campaign)
