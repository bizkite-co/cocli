import logging
import re
from playwright.async_api import Page
from .utils import calculate_zoom_level

logger = logging.getLogger(__name__)

class Navigator:
    def __init__(self, page: Page):
        self.page = page

    async def goto(self, lat: float, lon: float, width_miles: float, height_miles: float, query: str = "") -> bool:
        """
        Navigates the browser to the specified location and zoom level.
        If a query is provided, uses the /search/ URL structure.
        Otherwise, uses the basic view URL.
        """
        viewport = self.page.viewport_size
        width_px = viewport['width'] if viewport else 1920
        
        zoom_level = calculate_zoom_level(lat, width_miles, width_px)
        
        # Ensure zoom is within reasonable Google Maps bounds (approx 3 to 21)
        # 15z is standard "Streets"
        zoom_level = max(3.0, min(21.0, zoom_level))
        
        if query:
            # URL encode query if needed (basic replacement, better to use urllib)
            safe_query = query.replace(" ", "+")
            url = f"https://www.google.com/maps/search/{safe_query}/@{lat},{lon},{zoom_level:.2f}z?entry=ttu"
        else:
            url = f"https://www.google.com/maps/@{lat},{lon},{zoom_level:.2f}z?entry=ttu"

        logger.debug(f"Navigating to: {url} (Calculated Zoom: {zoom_level:.2f})")

        try:
            await self.page.goto(url, wait_until="commit", timeout=60000)
            
            # Wait for meaningful content
            # If searching, wait for the results feed or "no results" message
            if query:
                try:
                    # Either the feed appears OR "No results found" OR "Google Maps" canvas
                    # We'll wait for the canvas as a baseline
                    await self.page.wait_for_selector("canvas", timeout=30000)
                except Exception:
                     logger.warning("Map canvas not detected after navigation.")
            else:
                 await self.page.wait_for_selector("canvas", timeout=30000)
                 
            return True
        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            return False
            
    async def click_search_this_area(self) -> bool:
        """
        Clicks the 'Search this area' button if visible. 
        Useful if we panned instead of full reload, or if Google didn't auto-search.
        """
        try:
            button = self.page.get_by_role("button", name=re.compile("Search this area", re.IGNORECASE))
            if await button.is_visible():
                await button.click()
                await self.page.wait_for_timeout(2000) # Wait for update
                return True
        except Exception:
            pass
        return False
