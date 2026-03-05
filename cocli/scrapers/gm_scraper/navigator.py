import logging
import re
from playwright.async_api import Page

logger = logging.getLogger(__name__)

class Navigator:
    def __init__(self, page: Page):
        self.page = page

    async def goto(self, lat: float, lon: float, width_miles: float, height_miles: float, query: str = "") -> bool:
        """
        Navigates the browser using a high-fidelity 'Human' flow.
        """
        # 1. Go to Home Page first to establish session
        home_url = "https://www.google.com/maps/@34.2499124,-118.2605756,13z?hl=en-US"
        try:
            logger.info("Navigating to Google Maps Home...")
            # We use 'load' here because 'networkidle' can take too long on Maps
            await self.page.goto(home_url, wait_until="load", timeout=60000)
            # Wait for either the search box OR the map canvas to be ready
            await self.page.locator("#searchboxinput, canvas").first.wait_for(timeout=30000)
        except Exception as e:
            logger.error(f"Home navigation failed: {e}")
            return False

        if query:
            try:
                # 2. Find search box and type query
                search_box = self.page.locator('#searchboxinput, input[aria-label*="Search"], input[name="q"]').first
                await search_box.wait_for(state="visible", timeout=10000)
                await search_box.fill(query)
                
                # 3. Trigger Search
                await self.keyboard_search()
                
                # Wait for feed OR articles
                try:
                    await self.page.locator('div[role="feed"], div[role="article"]').first.wait_for(state="visible", timeout=15000)
                    return True
                except Exception:
                    logger.info("Search simulation didn't show results quickly. Falling back to direct URL...")
                    # FALLBACK: Direct URL Jump if simulation hangs
                    safe_query = query.replace(" ", "+")
                    search_url = f"https://www.google.com/maps/search/{safe_query}/@{lat},{lon},13z"
                    await self.page.goto(search_url, wait_until="load", timeout=60000)
                    await self.page.locator('div[role="feed"], div[role="article"]').first.wait_for(state="visible", timeout=30000)
                    return True
            except Exception as e:
                logger.error(f"Search flow failed: {e}")
                try:
                    safe_query = query.replace(" ", "+")
                    search_url = f"https://www.google.com/maps/search/{safe_query}/@{lat},{lon},13z"
                    await self.page.goto(search_url, wait_until="load", timeout=60000)
                    return True
                except Exception:
                    return False
        
        return True

    async def keyboard_search(self) -> None:
        """Helper to press Enter."""
        await self.page.keyboard.press("Enter")
            
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
