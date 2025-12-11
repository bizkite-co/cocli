import logging
from typing import List, AsyncIterator
from playwright.async_api import Browser
from geopy.distance import geodesic # type: ignore

from ...models.google_maps import GoogleMapsData
from .navigator import Navigator
from .strategy import SpiralStrategy
from .wilderness import WildernessManager
from .scanner import SidebarScraper
from .utils import get_viewport_bounds

logger = logging.getLogger(__name__)

class ScrapeCoordinator:
    def __init__(
        self,
        browser: Browser,
        campaign_name: str,
        base_width_miles: float = 2.0,
        base_height_miles: float = 1.0,
        viewport_width: int = 2000,
        viewport_height: int = 2000,
        debug: bool = False
    ):
        self.browser = browser
        self.campaign_name = campaign_name
        self.base_width_miles = base_width_miles
        self.base_height_miles = base_height_miles
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.debug = debug
        self.wilderness = WildernessManager()

    async def run(
        self,
        start_lat: float,
        start_lon: float,
        search_phrases: List[str],
        max_proximity_miles: float = 0.0,
        panning_distance_miles: int = 5,
        force_refresh: bool = False,
        ttl_days: int = 30
    ) -> AsyncIterator[GoogleMapsData]:
        
        # Create a new page for this session
        page = await self.browser.new_page(viewport={'width': self.viewport_width, 'height': self.viewport_height})
        navigator = Navigator(page)
        scanner = SidebarScraper(page, debug=self.debug)
        
        strategy = SpiralStrategy(start_lat, start_lon, panning_distance_miles)
        
        processed_ids: set[str] = set()
        
        try:
            for lat, lon in strategy:
                # 1. Proximity Check
                dist = geodesic((start_lat, start_lon), (lat, lon)).miles
                if max_proximity_miles > 0 and dist > max_proximity_miles:
                    logger.info(f"Reached max proximity ({dist:.2f} > {max_proximity_miles} miles). Stopping.")
                    break
                
                logger.info(f"Processing location: {lat:.4f}, {lon:.4f} (Dist: {dist:.1f} mi)")
                
                # 2. Determine Scope (Expand-Out)
                # We attempt to define the largest effective box for this center point
                # For now, simplistic approach: Use base size. 
                # Future: Implement the dynamic expansion loop here.
                
                # Let's implement a simple "Check if we can use a bigger zoom" logic
                # Loop through expansion factors: 1x, 2x, 4x...
                # If we find a box that is NOT wilderness and NOT scraped, we use it.
                # If we find a box that IS wilderness, we mark/skip.
                
                current_width = self.base_width_miles
                current_height = self.base_height_miles
                
                # Check if this area is already covered
                bounds = get_viewport_bounds(lat, lon, current_width, current_height)
                
                # If entirely wilderness, skip
                # (WildernessManager handles the index check)
                
                # Scrape each query
                for query in search_phrases:
                    if not self.wilderness.should_scrape(bounds, query):
                        logger.info(f"Skipping '{query}' at {lat},{lon} (Already covered/wilderness).")
                        continue
                        
                    # Navigate with CORRECT ZOOM
                    success = await navigator.goto(lat, lon, current_width, current_height, query)
                    if not success:
                        continue
                        
                    # Calculate ACTUAL dimensions from map scale
                    actual_width, actual_height = await navigator.get_current_map_dimensions()
                    
                    # Use actuals if available, otherwise fallback to planned
                    record_width = actual_width if actual_width > 0 else current_width
                    record_height = actual_height if actual_height > 0 else current_height
                        
                    # Scrape
                    items_found = 0
                    async for item in scanner.scrape(query, processed_ids, force_refresh, ttl_days):
                        yield item
                        items_found += 1
                        
                    # Mark Index
                    self.wilderness.mark_scraped(bounds, query, items_found, record_width, record_height)
                    
        finally:
            await page.close()
