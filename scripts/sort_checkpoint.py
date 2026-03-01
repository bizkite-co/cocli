# POLICY: frictionless-data-policy-enforcement
import logging
import sys
from cocli.core.prospect_compactor import compact_prospects_to_checkpoint

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("sorter_worker")

def sort_checkpoint(campaign_name: str) -> None:
    """
    Sorter Worker: Thin wrapper around the Unified Compaction Engine.
    Ensures the index is stably sorted and deduped using the official project logic.
    """
    logger.info(f"--- Sorter Worker: {campaign_name} ---")
    compact_prospects_to_checkpoint(campaign_name)

if __name__ == "__main__":
    from cocli.core.config import get_campaign
    campaign = sys.argv[1] if len(sys.argv) > 1 else get_campaign()
    if not campaign:
        print("No campaign specified.")
        sys.exit(1)
    sort_checkpoint(campaign)
