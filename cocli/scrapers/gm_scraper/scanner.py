import logging
from typing import AsyncIterator, Set, Optional
from playwright.async_api import Page

from ...core.config import load_scraper_settings
from ...models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem
from ..google_maps_parser import parse_business_listing_html

logger = logging.getLogger(__name__)

class SidebarScraper:
    def __init__(self, page: Page, debug: bool = False):
        self.page = page
        self.debug = debug
        self.settings = load_scraper_settings()

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
        delay_seconds = self.settings.google_maps_delay_seconds

        logger.info(f"Scanning sidebar for: '{search_string}'")

        if self.page.is_closed():
            return

        # Ensure search box is filled and search is triggered
        # Note: If we navigated via URL with query, this might already be populated,
        # but pressing Enter ensures the specific list is active?
        # Actually, navigating to /search/query/... usually opens the list automatically.
        # But we need to find the scrollable div.
        
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

            # Process new divs
            for i in range(last_processed_div_count, len(listing_divs)):
                if self.page.is_closed():
                    break
                    
                listing_div = listing_divs[i]
                
                # Fetch HTML
                html_content = ""
                try:
                    html_content = await listing_div.inner_html(timeout=2000)
                except Exception:
                    continue

                if not html_content or "All filters" in html_content or "Prices come from Google" in html_content:
                    continue

                # Parse
                try:
                    business_data_dict = parse_business_listing_html(html_content, search_string, debug=self.debug)
                except Exception:
                    continue

                place_id = business_data_dict.get("Place_ID")
                name = business_data_dict.get("Name")
                if not place_id or not name or name == "Unknown" or len(name) < 3 or place_id in processed_place_ids:
                    continue

                from ...core.text_utils import slugify
                processed_place_ids.add(place_id)

                # Yield Discovery Item
                yield GoogleMapsListItem(
                    place_id=place_id,
                    name=name,
                    company_slug=slugify(name),
                    phone=business_data_dict.get("Phone_1"),
                    gmb_url=business_data_dict.get("GMB_URL"),
                    discovery_phrase=search_string,
                    discovery_tile_id=tile_id
                )

            last_processed_div_count = len(listing_divs)

            # Check for "End of list"
            if await self.page.get_by_text("You've reached the end of the list").is_visible():
                break

            try:
                await scrollable_div.hover()
                await self.page.mouse.wheel(0, 5000)
                await self.page.wait_for_timeout(delay_seconds * 1000)
            except Exception:
                break
