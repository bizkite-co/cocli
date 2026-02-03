import logging
import asyncio
from typing import Optional
from playwright.async_api import Page

from cocli.models.google_maps_prospect import GoogleMapsProspect
from cocli.scrapers.google_maps_gmb_parser import parse_gmb_page

logger = logging.getLogger(__name__)

async def scrape_google_maps_details(
    page: Page,
    place_id: str,
    campaign_name: str,
    name: Optional[str] = None,
    company_slug: Optional[str] = None,
    debug: bool = False
) -> Optional[GoogleMapsProspect]:
    """
    Scrapes full details for a given Google Maps Place ID.
    Uses semantic selectors and provided identity fallbacks to prevent hollow records.
    """
    gmb_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
    
    logger.info(f"Scraping details for Place ID: {place_id}")

    try:
        await page.goto(gmb_url, wait_until="load", timeout=60000)
        # Wait specifically for the name headline OR the main detail pane
        await page.wait_for_selector('h1, div[role="main"], .qBF1Pd', timeout=30000)
        await asyncio.sleep(5) # Give dynamic data time to settle

        html_content = await page.content()
        details_dict = parse_gmb_page(html_content, debug=debug)
        
        from cocli.models.google_maps_raw import GoogleMapsRawResult
        
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
            GMB_URL=gmb_url,
            processed_by="details-worker"
        )
        
        # EXPLICIT VALIDATION: This triggers the Pydantic Shield
        try:
            prospect = GoogleMapsProspect.from_raw(raw_result)
            if company_slug:
                prospect.company_slug = company_slug # Override if we have a proven slug
            return prospect
        except Exception as val_err:
            logger.error(f"IDENTITY SHIELD: Validation failed for {place_id}: {val_err}")
            return None

    except Exception as e:
        logger.error(f"Error scraping details for Place ID {place_id}: {e}")
        return None