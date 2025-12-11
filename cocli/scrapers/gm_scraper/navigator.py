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
        # Google Maps often rejects decimal zoom levels in the URL, resetting to default (e.g. 9z).
        # We round to the nearest integer to ensure stability.
        zoom_level = max(3, min(21, round(zoom_level)))
        
        if query:
            # URL encode query if needed (basic replacement, better to use urllib)
            safe_query = query.replace(" ", "+")
            url = f"https://www.google.com/maps/search/{safe_query}/@{lat},{lon},{zoom_level}z?entry=ttu"
        else:
            url = f"https://www.google.com/maps/@{lat},{lon},{zoom_level}z?entry=ttu"

        logger.debug(f"Navigating to: {url} (Calculated Zoom: {zoom_level})")

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

    async def get_current_map_dimensions(self) -> tuple[float, float]:
        """
        Calculates the actual visible map dimensions in miles by reading the scale element.
        Returns (width_miles, height_miles).
        Returns (0.0, 0.0) if calculation fails.
        """
        try:
            # 1. Get Scale Text (e.g., "50 mi")
            scale_label = self.page.locator("#scale label")
            if not await scale_label.is_visible():
                # Try finding by ID if generic selector fails (backup based on HTML dump)
                scale_label = self.page.locator("#U5ELMd") 
                if not await scale_label.is_visible():
                    logger.warning("Scale label not found.")
                    return 0.0, 0.0
            
            scale_text = await scale_label.text_content()
            if not scale_text:
                return 0.0, 0.0

            # 2. Get Scale Bar Width (pixels)
            # The bar is a div sibling to the label or inside the button
            scale_bar = self.page.locator("#scale div[style*='width']")
            if not await scale_bar.is_visible():
                 scale_bar = self.page.locator(".Ty7QWe") # Class from HTML dump
                 if not await scale_bar.is_visible():
                    logger.warning("Scale bar not found.")
                    return 0.0, 0.0
            
            # Extract width from style or bounding box
            # bounding_box is more reliable than parsing style string
            box = await scale_bar.bounding_box()
            if not box or box['width'] == 0:
                logger.warning("Scale bar has no width.")
                return 0.0, 0.0
            
            scale_width_px = box['width']

            # 3. Parse Distance
            # Matches number and unit (mi, ft, km, m)
            match = re.match(r"([\d\.]+)\s*(mi|ft|km|m)", scale_text.strip(), re.IGNORECASE)
            if not match:
                logger.warning(f"Could not parse scale text: '{scale_text}'")
                return 0.0, 0.0
            
            value = float(match.group(1))
            unit = match.group(2).lower()
            
            scale_miles = 0.0
            if unit == 'mi':
                scale_miles = value
            elif unit == 'ft':
                scale_miles = value / 5280.0
            elif unit == 'km':
                scale_miles = value * 0.621371
            elif unit == 'm':
                scale_miles = (value / 1000.0) * 0.621371
            
            # 4. Calculate Dimensions
            viewport = self.page.viewport_size
            if not viewport:
                return 0.0, 0.0
                
            miles_per_pixel = scale_miles / scale_width_px
            
            width_miles = viewport['width'] * miles_per_pixel
            height_miles = viewport['height'] * miles_per_pixel
            
            logger.info(f"Map Scale: {scale_text} = {scale_width_px}px. Actual Viewport: {width_miles:.3f} x {height_miles:.3f} miles")
            
            return width_miles, height_miles

        except Exception as e:
            logger.error(f"Error calculating map dimensions: {e}")
            return 0.0, 0.0
