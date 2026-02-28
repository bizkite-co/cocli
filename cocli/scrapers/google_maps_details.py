import logging
from typing import Optional, TYPE_CHECKING
from playwright.async_api import Page

from cocli.models.campaigns.raw_witness import RawWitness
from .gm_details_scraper import GoogleMapsDetailsScraper

if TYPE_CHECKING:
    from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

logger = logging.getLogger(__name__)

async def capture_google_maps_raw(
    page: Page,
    place_id: str,
    campaign_name: str,
    processed_by: str = "local-scraper",
    debug: bool = False
) -> Optional[RawWitness]:
    """
    Navigates to a Google Maps place and captures the raw HTML and basic metadata.
    Uses the GoogleMapsDetailsScraper state machine for robust execution.
    """
    scraper = GoogleMapsDetailsScraper(page, campaign_name, processed_by)
    return await scraper.scrape(place_id)

async def scrape_google_maps_details(
    page: Page,
    place_id: str,
    campaign_name: str,
    name: Optional[str] = None,
    company_slug: Optional[str] = None,
    debug: bool = False
) -> Optional["GoogleMapsProspect"]:
    """
    Scrapes full details for a given Google Maps Place ID.
    Uses the state machine for capture and then parses the result.
    """
    from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
    from cocli.models.campaigns.indexes.google_maps_raw import GoogleMapsRawResult
    from cocli.scrapers.google_maps_gmb_parser import parse_gmb_page

    # Execute state-machine capture
    witness = await capture_google_maps_raw(page, place_id, campaign_name, debug=debug)
    if not witness:
        return None

    # Parse with GMB parser
    details_dict = parse_gmb_page(witness.html, debug=debug)
    
    # Merge parsed data with provided fallbacks
    final_name = details_dict.get("Name") or name
    if not final_name:
        logger.error(f"IDENTITY SHIELD: No name found for {place_id} and no fallback provided. Blocking save.")
        return None

    raw_result = GoogleMapsRawResult(
        Place_ID=place_id,
        Name=final_name,
        Full_Address=details_dict.get("Full_Address", ""),
        Website=details_dict.get("Website", ""),
        Phone_1=details_dict.get("Phone", ""),
        Reviews_count=details_dict.get("Reviews_count"),
        Average_rating=details_dict.get("Average_rating"),
        GMB_URL=witness.url,
        processed_by=witness.processed_by
    )
    
    try:
        prospect = GoogleMapsProspect.from_raw(raw_result)
        if company_slug:
            prospect.company_slug = company_slug 
        return prospect
    except Exception as val_err:
        logger.error(f"IDENTITY SHIELD: Validation failed for {place_id}: {val_err}")
        return None
