import logging
import asyncio
from typing import Optional
from playwright.async_api import Page

from cocli.models.campaigns.raw_witness import RawWitness

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
    Uses a 'Pre-Flight Warmup' to establish session state and avoid 'Limited View'.
    """
    gmb_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
    logger.info(f"Capturing RAW for Place ID: {place_id}")

    # 0. PRE-FLIGHT WARMUP: Establish session state
    try:
        logger.debug("Establishing session at google.com/maps...")
        # Check if we are already on google maps to avoid redundant warmup
        if not page.url.startswith("https://www.google.com/maps"):
            await page.goto("https://www.google.com/maps", wait_until="commit", timeout=20000)
            await asyncio.sleep(2)
    except Exception as warmup_err:
        logger.warning(f"Warmup failed (continuing anyway): {warmup_err}")

    try:
        # 1. NAVIGATE TO TARGET
        await page.goto(gmb_url, wait_until="load", timeout=60000)
        # Wait for the sidebar to stabilize
        await page.wait_for_selector('h1, div[role="main"], .qBF1Pd', timeout=30000)
        await asyncio.sleep(5) 

        # 2. SESSION-HEAL: Trigger hydration click to reveal full review data
        hydration_triggers = [
            'div.F7nice', 
            'button[jsaction*="pane.rating.moreReviews"]',
            'div[jsaction*="reviewChart.moreReviews"]',
            'span[aria-label*="stars"]'
        ]
        
        for selector in hydration_triggers:
            try:
                # Use a longer wait and explicit click
                el = await page.wait_for_selector(selector, timeout=5000)
                if el:
                    logger.debug(f"Triggering hydration click for high-fidelity witness: {place_id} via {selector}")
                    await el.click()
                    # Wait long enough for the 'Full' data to replace 'Lite' data
                    await asyncio.sleep(5) 
                    break
            except Exception:
                continue

        html_content = await page.content()
        
        return RawWitness(
            place_id=place_id,
            processed_by=processed_by,
            campaign_name=campaign_name,
            url=gmb_url,
            html=html_content,
            metadata={
                "capture_strategy": "direct-place-id",
                "viewport": str(page.viewport_size)
            }
        )

    except Exception as e:
        logger.error(f"Error capturing raw for {place_id}: {e}")
        return None

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
    Uses 'Pre-Flight Warmup' and 'Session-Heal' hydration.
    """
    from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
    from cocli.models.campaigns.indexes.google_maps_raw import GoogleMapsRawResult
    from cocli.scrapers.google_maps_gmb_parser import parse_gmb_page

    witness = await capture_google_maps_raw(page, place_id, campaign_name, debug=debug)
    if not witness:
        return None

    # Parse with GMB parser (which uses the modular ultra-robust parsers)
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
        processed_by="details-worker"
    )
    
    try:
        prospect = GoogleMapsProspect.from_raw(raw_result)
        if company_slug:
            prospect.company_slug = company_slug 
        return prospect
    except Exception as val_err:
        logger.error(f"IDENTITY SHIELD: Validation failed for {place_id}: {val_err}")
        return None
