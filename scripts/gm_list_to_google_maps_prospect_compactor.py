# POLICY: frictionless-data-policy-enforcement
import logging
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.core.paths import paths
from cocli.utils.usv_utils import USVReader
from cocli.core.prospect_compactor import compact_prospects_to_checkpoint
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.core.prospects_csv_manager import ProspectsIndexManager

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(".logs/gm_list_to_prospect_compactor.log", mode='a'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("gm_list_to_prospect_compactor")

async def gm_list_to_google_maps_prospect_compact(campaign_name: str) -> None:
    """
    Specialized Compactor: Merges GM List discovery traces (USVs) directly into the 
    Google Maps Prospect Gold Checkpoint.
    
    UPDATES: 
    1. Rating, 2. Review count, 3. Domain/Website, 4. GMB_URL, 5. Street Address
    """
    campaign_node = paths.campaign(campaign_name)
    results_dir = campaign_node.path / "queues" / "gm-list" / "completed" / "results"
    idx_manager = ProspectsIndexManager(campaign_name)
    
    if not results_dir.exists():
        logger.warning(f"No discovery results found at {results_dir}")
        return

    logger.info(f"--- GM List to Prospect Compactor: {campaign_name} ---")
    
    # 1. Scan for USV Trace Files
    trace_files = list(results_dir.rglob("*.usv"))
    logger.info(f"Scanning {len(trace_files)} discovery trace files...")
    
    total_prospects = 0
    saved_count = 0
    
    for trace_path in trace_files:
        try:
            with open(trace_path, "r", encoding="utf-8") as f:
                reader = USVReader(f)
                for row in reader:
                    # Discovery Trace Schema (9 fields):
                    # 0: place_id, 1: slug, 2: name, 3: phone, 4: domain, 5: reviews, 6: rating, 7: address, 8: gmb_url
                    if len(row) >= 9:
                        total_prospects += 1
                        pid = row[0]
                        
                        try:
                            from cocli.models.campaigns.indexes.google_maps_raw import GoogleMapsRawResult
                            raw = GoogleMapsRawResult(
                                Place_ID=pid,
                                Name=row[2],
                                Full_Address=row[7], # Maps to street_address via from_raw validator
                                Website=row[4] if "." in row[4] else "",
                                Phone_1=row[3],
                                Domain=row[4],
                                Average_rating=float(row[6]) if row[6] else None,
                                Reviews_count=int(row[5]) if row[5] else None,
                                GMB_URL=row[8],
                                processed_by="gm-list-compactor"
                            )
                            
                            prospect = GoogleMapsProspect.from_raw(raw)
                            # Timestamp update via from_raw ensures these 'win' over old records
                            if idx_manager.append_prospect(prospect):
                                saved_count += 1
                                
                        except Exception as e:
                            logger.debug(f"Failed to transform row for {pid}: {e}")
                            
        except Exception as e:
            logger.error(f"Failed to read trace {trace_path}: {e}")

    logger.info(f"Scan complete. Found {total_prospects} prospects in traces, appended {saved_count} to WAL.")
    
    # 2. Compact WAL into Checkpoint (Using Unified Sort Engine)
    if saved_count > 0:
        logger.info("Committing discovery records to Gold Checkpoint via Unified Engine...")
        compact_prospects_to_checkpoint(campaign_name)
        logger.info("Gold Checkpoint updated and stably sorted.")

if __name__ == "__main__":
    from cocli.core.config import get_campaign
    import sys
    campaign = sys.argv[1] if len(sys.argv) > 1 else get_campaign()
    if not campaign:
        print("No campaign specified.")
        sys.exit(1)
    asyncio.run(gm_list_to_google_maps_prospect_compact(campaign))
