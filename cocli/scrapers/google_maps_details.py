import logging
import asyncio
from typing import Optional
from playwright.async_api import Page

from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.scrapers.google_maps_gmb_parser import parse_gmb_page
from ..models.campaigns.raw_witness import RawWitness

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
    Does NOT parse the HTML into a prospect model.
    """
    gmb_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
    logger.info(f"Capturing RAW for Place ID: {place_id}")

    try:
        await page.goto(gmb_url, wait_until="load", timeout=60000)
        await page.wait_for_selector('h1, div[role="main"], .qBF1Pd', timeout=30000)
        await asyncio.sleep(5) 

        # SESSION-HEAL: If we want high-fidelity capture, we trigger hydration now
        # so the 'Witness' contains the full review data for later processing.
        hydration_triggers = [
            'div.F7nice', 
            'button[jsaction*="pane.rating.moreReviews"]',
            'div[jsaction*="reviewChart.moreReviews"]',
            'span[aria-label*="stars"]'
        ]
        
        for selector in hydration_triggers:
            try:
                # Use a short timeout to check each trigger
                if await page.is_visible(selector):
                    logger.debug(f"Triggering hydration click for high-fidelity witness: {place_id} via {selector}")
                    await page.click(selector)
                    await asyncio.sleep(3) # Wait for dynamic load
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
        
        from cocli.models.campaigns.indexes.google_maps_raw import GoogleMapsRawResult
        
        # Merge parsed data with provided fallbacks
        final_name = details_dict.get("Name")
        
        # IDENTITY SHIELD: Reject SEO junk or generic recovery names
        if not final_name or final_name.lower() in ["home", "homepage", "home page"]:
            # Only use the provided 'name' if it's not a generic recovery title
            if name and "recovery task" not in name.lower() and name.lower() not in ["home", "homepage"]:
                final_name = name
            else:
                final_name = None
        
        if not final_name:
            logger.error(f"IDENTITY SHIELD: No valid name found for {place_id} (Scraped: {details_dict.get('Name')}, Fallback: {name}). Blocking save.")
            return None

        # 1. Start with the dictionary from the parser
        # Ensure we map GMB parser keys ('Phone', etc) to RawResult keys ('Phone_1', etc)
        raw_data = {
            "Place_ID": place_id,
            "Name": final_name,
            "Full_Address": details_dict.get("Full_Address", ""),
            "Website": details_dict.get("Website", ""),
            "Phone_1": details_dict.get("Phone", ""),
            "Domain": details_dict.get("Domain", ""),
            "Average_rating": details_dict.get("Average_rating"),
            "Reviews_count": details_dict.get("Reviews_count"),
            "GMB_URL": gmb_url,
            "processed_by": "details-worker"
        }
        
        # Add any other fields from details_dict that might be present
        for k, v in details_dict.items():
            if k not in raw_data and k in GoogleMapsRawResult.model_fields:
                raw_data[k] = v
                
        raw_result = GoogleMapsRawResult(**raw_data)
        
        logger.debug(f"Pre-Heal Check for {place_id}: Rating={raw_result.Average_rating}, Reviews={raw_result.Reviews_count}")
        
        # --- SESSION-HEAL: Force Hydration if Limited View detected ---
        if not raw_result.Average_rating or not raw_result.Reviews_count:
            try:
                # We try several possible triggers for the reviews pane
                triggers = [
                    'div.F7nice', 
                    'span[aria-label*="stars"]',
                    'button:has-text("reviews")',
                    'button[aria-label*="reviews"]'
                ]
                
                clicked = False
                for selector in triggers:
                    if await page.is_visible(selector):
                        logger.info(f"CLOAK DETECTED for {place_id}. Triggering hydration via: {selector}")
                        await page.click(selector)
                        clicked = True
                        break
                
                if clicked:
                    await asyncio.sleep(5) # Wait for dynamic load
                    
                    # Re-parse the healed page
                    new_html = await page.content()
                    healed_data = parse_gmb_page(new_html, debug=debug)
                    
                    # Update our raw_result with any new findings
                    updated_fields = []
                    for k, v in healed_data.items():
                        if v and hasattr(raw_result, k) and not getattr(raw_result, k):
                            setattr(raw_result, k, v)
                            updated_fields.append(k)
                    
                    if updated_fields:
                        logger.info(f"HYDRATION SUCCESS for {place_id}! Fields recovered: {', '.join(updated_fields)}")
                    else:
                        logger.warning(f"Hydration click executed for {place_id}, but no new data recovered.")
                else:
                    logger.warning(f"No hydration triggers found for {place_id}. Page may be severely cloaked.")
                    
            except Exception as heal_err:
                logger.debug(f"Hydration click failed: {heal_err}")

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