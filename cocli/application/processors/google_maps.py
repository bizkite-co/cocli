# POLICY: frictionless-data-policy-enforcement
import logging
from datetime import datetime, UTC
from typing import Any, Optional

from ...models.campaigns.queues.gm_details import GmItemTask
from ...models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from ...scrapers.google_maps_details import scrape_google_maps_details
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
            # If we already have data for this place, don't overwrite good fields with nulls
            existing = GoogleMapsProspect.get_by_place_id(task.campaign_name, task.place_id)
            if existing:
                logger.info(f"Merging new data with existing prospect: {task.place_id}")
                prospect = prospect.merge_with_existing(existing)

            # 3. Metadata Hydration
            prospect.processed_by = self.processed_by
            prospect.updated_at = datetime.now(UTC)
            prospect.discovery_phrase = task.discovery_phrase
            prospect.discovery_tile_id = task.discovery_tile_id

            # 4. Save to Hot Index (WAL)
            # This is the sharded campaign-level storage for DuckDB/Compaction
            csv_manager = ProspectsIndexManager(task.campaign_name)
            if csv_manager.append_prospect(prospect):
                logger.info(f"Saved to Campaign WAL: {task.place_id}")
            else:
                logger.error(f"Failed to save to Campaign WAL: {task.place_id}")

            # 4. Save to Company Enrichment
            # This is the company-level isolated storage
            if prospect.company_slug:
                try:
                    enrich_path = prospect.save_enrichment()
                    logger.info(f"Saved to Company Enrichment: {enrich_path}")
                except Exception as e:
                    logger.error(f"Failed to save Company Enrichment for {prospect.company_slug}: {e}")

            return prospect

        except Exception as e:
            logger.error(f"Processor error for {task.place_id}: {e}", exc_info=True)
            return None
