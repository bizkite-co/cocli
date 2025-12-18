import logging
from datetime import datetime, timedelta, UTC
from typing import AsyncIterator, Set, Dict, Any
from playwright.async_api import Page

from ...core.config import load_scraper_settings
from ...core.google_maps_cache import GoogleMapsCache
from ...models.google_maps_prospect import GoogleMapsProspect
from ..google_maps_parser import parse_business_listing_html
from ..google_maps_gmb_parser import parse_gmb_page

logger = logging.getLogger(__name__)

class SidebarScraper:
    def __init__(self, page: Page, debug: bool = False):
        self.page = page
        self.debug = debug
        self.settings = load_scraper_settings()
        self.cache = GoogleMapsCache()

    async def scrape(
        self,
        search_string: str,
        processed_place_ids: Set[str],
        force_refresh: bool,
        ttl_days: int
    ) -> AsyncIterator[GoogleMapsProspect]:
        """
        Scrapes the sidebar results for the current map view.
        """
        delay_seconds = self.settings.google_maps_delay_seconds
        fresh_delta = timedelta(days=ttl_days)

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
                if not place_id or place_id in processed_place_ids:
                    continue

                processed_place_ids.add(place_id)

                # Cache Check
                cached_item = self.cache.get_by_place_id(place_id)
                if cached_item and not force_refresh and (datetime.now(UTC) - cached_item.updated_at < fresh_delta):
                    yield cached_item
                    continue

                # GMB Detail Check (if missing crucial info)
                gmb_url = business_data_dict.get("GMB_URL")
                if gmb_url and (not business_data_dict.get("Website") or not business_data_dict.get("Full_Address")):
                     await self._fetch_gmb_details(gmb_url, business_data_dict)

                # Yield
                business_data = GoogleMapsProspect(**business_data_dict)
                self.cache.add_or_update(business_data)
                yield business_data

            last_processed_div_count = len(listing_divs)

            # Check for "End of list"
            if await self.page.get_by_text("You've reached the end of the list").is_visible():
                break

            # Scroll
            try:
                await scrollable_div.hover()
                await self.page.mouse.wheel(0, 5000)
                await self.page.wait_for_timeout(delay_seconds * 1000)
            except Exception:
                break
                
    async def _fetch_gmb_details(self, url: str, data_dict: Dict[str, Any]) -> None:
        try:
            # Open new page/context to not disrupt main flow?
            # Or just use current page? 
            # Using current page disrupts the list state. 
            # Must use a new page.
            context = self.page.context
            page = await context.new_page()
            try:
                await page.goto(url, timeout=60000)
                html = await page.content()
                details = parse_gmb_page(html)
                data_dict.update(details)
            finally:
                await page.close()
        except Exception as e:
            logger.warning(f"GMB detail fetch failed: {e}")
