# POLICY: frictionless-data-policy-enforcement
import logging
from datetime import datetime, UTC
from typing import Any, Optional

from ...models.campaigns.queues.gm_details import GmItemTask
from ...models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from ...scrapers.google.google_maps_details import scrape_google_maps_details
from ...core.prospects_csv_manager import ProspectsIndexManager

logger = logging.getLogger(__name__)

class GoogleMapsDetailsProcessor:
    """
    Modular processor for Google Maps Detail tasks.
    Adheres to ADR-001 (Model-to-Model transformation).
    
    Source: GmItemTask (Queue)
    Output: GoogleMapsProspect (WAL + Enrichment)
    """
    
    def __init__(self, processed_by: str = "local-processor"):
        self.processed_by = processed_by

    async def process(self, task: GmItemTask, page: Any, debug: bool = False) -> Optional[GoogleMapsProspect]:
        """
        Executes the detail scrape and saves results to both the Hot Index (WAL) 
        and the Company Enrichment directory.
        
        Mandate: This processor DOES NOT touch the company _index.md.
        """
        logger.info(f"Processing Details for: {task.place_id} ({task.company_slug})")
        
        try:
            # 1. Scrape Raw Data -> Model (GoogleMapsProspect)
            prospect = await scrape_google_maps_details(
                page=page,
                place_id=task.place_id,
                campaign_name=task.campaign_name,
                name=task.name,
                company_slug=task.company_slug,
                debug=debug
            )
            
            if not prospect:
                logger.warning(f"No data returned for Place ID: {task.place_id}")
                return None

            # 2. Non-Destructive Merge with Existing Data
            # Note: merge_with_existing handles updated_at refresh
            existing = GoogleMapsProspect.get_by_place_id(task.campaign_name, task.place_id)
            if existing:
                logger.info(f"Merging new data with existing prospect: {task.place_id}")
                prospect = prospect.merge_with_existing(existing)

            # 3. Metadata Hydration
            prospect.processed_by = self.processed_by
            prospect.updated_at = datetime.now(UTC)

            # 4. Durability Tier (WAL)
            # We append to the Write-Ahead Log for later compaction
            index_manager = ProspectsIndexManager(task.campaign_name)
            wal_path = index_manager.add_to_wal(prospect)
            logger.info(f"Appended to WAL: {wal_path}")

            # 5. Save to Company Enrichment
            # This ensures the business data is attached to the company for the TUI/Frontend
            enrichment_path = prospect.save_enrichment()
            logger.info(f"Saved company enrichment: {enrichment_path}")

            return prospect

        except Exception as e:
            logger.error(f"Error processing detail task for {task.place_id}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
