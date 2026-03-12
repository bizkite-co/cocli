# POLICY: frictionless-data-policy-enforcement
import logging
import re
from typing import AsyncIterator, Set, Optional
from playwright.async_api import Page, Locator

from ...core.config import load_scraper_settings
from ...core.text_utils import slugify
from ...models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem

logger = logging.getLogger(__name__)

class SidebarScraper:
    def __init__(self, page: Page, debug: bool = False):
        self.page = page
        self.debug = debug
        self.settings = load_scraper_settings()

    async def wait_for_hydration(self, listing_locator: Locator) -> bool:
        """
        Production-grade hydration wait. 
        Waits for the high-fidelity semantic ARIA label (stars + reviews) to appear.
        """
        combined_pattern = re.compile(r"\d\.\d\s*stars?\s*[\d,]+\s*Reviews?", re.IGNORECASE)
        
        try:
            await listing_locator.get_by_text(combined_pattern).first.wait_for(timeout=10000)
            return True
        except Exception:
            try:
                await listing_locator.locator('span[aria-label*="stars"]').first.wait_for(timeout=2000)
                return True
            except Exception:
                return False

    async def capture_listing_html(self, listing_locator: Locator) -> str:
        """Production method to capture the outerHTML of a listing div."""
        try:
            html = await listing_locator.evaluate("el => el.outerHTML")
            return str(html)
        except Exception:
            return ""

    async def scrape(
        self,
        search_string: str,
        processed_place_ids: Set[str],
        force_refresh: bool,
        ttl_days: int,
        tile_id: Optional[str] = None
    ) -> AsyncIterator[GoogleMapsListItem]:
        """
        Scrapes the sidebar results for the current map view.
        Yields GoogleMapsListItem for each found business.
        """
        from ..google_maps_parser import parse_business_listing_html

        logger.info(f"Scanning sidebar for: '{search_string}'")

        if self.page.is_closed():
            return

        try:
            scrollable_div_selector = 'div[role="feed"]'
            await self.page.wait_for_selector(scrollable_div_selector, timeout=20000)
            scrollable_div = self.page.locator(scrollable_div_selector)
        except Exception:
            logger.warning(f"Could not find scrollable results feed for '{search_string}'. Possibly no results.")
            return

        last_processed_div_count = 0
        consecutive_no_new_results = 0
        
        while True:
            if self.page.is_closed():
                break

            await self.page.wait_for_timeout(1000)
            listing_divs = await scrollable_div.locator("> div").all()
            
            if len(listing_divs) == last_processed_div_count:
                consecutive_no_new_results += 1
                if consecutive_no_new_results > 2:
                    logger.debug("No new results after scrolling. Stopping.")
                    break
            else:
                consecutive_no_new_results = 0

            for i in range(last_processed_div_count, len(listing_divs)):
                if self.page.is_closed():
                    break
                    
                listing_div = listing_divs[i]
                
                try:
                    box = await listing_div.bounding_box()
                    if box:
                        await self.page.mouse.move(box['x'] + box['width']/2, box['y'] + box['height']/2)
                        await self.page.mouse.wheel(0, 100)
                        await self.page.wait_for_timeout(500)
                except Exception:
                    pass

                await self.wait_for_hydration(listing_div)
                html_content = await self.capture_listing_html(listing_div)

                if not html_content or "All filters" in html_content or "Prices come from Google" in html_content:
                    continue

                data = parse_business_listing_html(html_content, search_string, debug=self.debug)
                place_id = data.get("Place_ID")

                if place_id and place_id not in processed_place_ids:
                    processed_place_ids.add(place_id)
                    
                    # Type-safe field extraction
                    raw_revs = data.get("Reviews_count")
                    revs = int(str(raw_revs).replace(",", "")) if raw_revs else None
                    
                    raw_rating = data.get("Average_rating")
                    rating = float(str(raw_rating)) if raw_rating else None

                    item = GoogleMapsListItem(
                        place_id=place_id,
                        name=data.get("Name", "Unknown"),
                        category=data.get("First_category"),
                        company_slug=data.get("company_slug", slugify(data.get("Name", place_id))),
                        phone=data.get("Phone_1"),
                        domain=data.get("Domain"),
                        reviews_count=revs,
                        average_rating=rating,
                        street_address=data.get("Street_Address"),
                        gmb_url=data.get("GMB_URL"),
                        discovery_phrase=search_string,
                        discovery_tile_id=tile_id,
                        html=html_content
                    )
                    yield item

            last_processed_div_count = len(listing_divs)
            
            try:
                await scrollable_div.hover()
                await self.page.mouse.wheel(0, 5000)
                await self.page.wait_for_timeout(2000)
            except Exception:
                break
