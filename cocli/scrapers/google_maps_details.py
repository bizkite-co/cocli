import logging
from typing import Optional
from playwright.async_api import Page

from ..models.google_maps_prospect import GoogleMapsProspect
from .google_maps_gmb_parser import parse_gmb_page

logger = logging.getLogger(__name__)

async def scrape_google_maps_details(
    page: Page,
    place_id: str,
    campaign_name: str, # Not strictly needed here, but for consistency
    debug: bool = False
) -> Optional[GoogleMapsProspect]:
    """
    Scrapes full details for a given Google Maps Place ID.
    Navigates directly to the GMB page and parses content.
    """
    gmb_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
    
    logger.info(f"Scraping details for Place ID: {place_id} from URL: {gmb_url}")

    try:
        await page.goto(gmb_url, timeout=60000) # 60 sec timeout for navigation
        await page.wait_for_selector('div[role="main"]', timeout=30000) # Wait for main content to load

        html_content = await page.content()
        details_dict = parse_gmb_page(html_content, debug=debug)
        
        if details_dict:
            # We don't have all prospect fields, just details.
            # So return a dict of the *extracted* details.
            # The worker will merge this with existing prospect data.
            details_dict['Place_ID'] = place_id # Ensure Place_ID is present
            return GoogleMapsProspect(**details_dict)
        else:
            logger.warning(f"No details parsed for Place ID: {place_id}")
            return None

    except Exception as e:
        logger.error(f"Error scraping details for Place ID {place_id}: {e}")
        if debug:
            await page.screenshot(path=f"debug_details_scrape_error_{place_id}.png")
        return None