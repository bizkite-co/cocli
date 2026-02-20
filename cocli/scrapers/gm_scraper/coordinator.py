import logging
from typing import List, AsyncIterator, Optional, Dict, Any, Union
from playwright.async_api import Browser
from geopy.distance import geodesic # type: ignore

from ...models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem
from .navigator import Navigator
from .strategy import SpiralStrategy, GridStrategy
from .wilderness import WildernessManager
from .scanner import SidebarScraper
from .utils import get_viewport_bounds
from ...utils.playwright_utils import setup_optimized_context, BandwidthTracker

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
        debug: bool = False,
        s3_client: Any = None,
        s3_bucket: Optional[str] = None
    ):
        self.browser = browser
        self.campaign_name = campaign_name
        self.base_width_miles = base_width_miles
        self.base_height_miles = base_height_miles
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.debug = debug
        self.wilderness = WildernessManager(s3_client=s3_client, s3_bucket=s3_bucket)
        self.bandwidth_tracker: Optional[BandwidthTracker] = None

    async def run(
        self,
        start_lat: float,
        start_lon: float,
        search_phrases: List[str],
        max_proximity_miles: float = 0.0,
        panning_distance_miles: int = 5,
        force_refresh: bool = False,
        ttl_days: int = 30,
        grid_tiles: Optional[List[Dict[str, Any]]] = None,
        processed_by: Optional[str] = None
    ) -> AsyncIterator[GoogleMapsListItem]:
        
        # Create a new context explicitly for this session
        # This fixes 'Please use browser.new_context()' errors on some environments
        context = await self.browser.new_context(viewport={'width': self.viewport_width, 'height': self.viewport_height})
        
        # Setup optimization (blocking images/css + tracking bandwidth)
        self.bandwidth_tracker = await setup_optimized_context(context)
        
        page = await context.new_page()
        
        navigator = Navigator(page)
        scanner = SidebarScraper(page, debug=self.debug)
        
        strategy: Union[SpiralStrategy, GridStrategy]
        if grid_tiles:
            logger.info(f"Using GridStrategy with {len(grid_tiles)} tiles.")
            strategy = GridStrategy(grid_tiles)
        else:
            logger.info("Using SpiralStrategy.")
            strategy = SpiralStrategy(start_lat, start_lon, panning_distance_miles)
        
        processed_ids: set[str] = set()
        
        try:
            for target in strategy:
                # Unpack target based on length to support both Spiral (2) and Grid (3) strategies
                tile_id = None
                if len(target) == 3:
                    lat, lon, tile_id = target
                else:
                    lat, lon = target

                # 1. Proximity Check (Skip for GridStrategy)
                dist = 0.0
                if not grid_tiles:
                    dist = geodesic((start_lat, start_lon), (lat, lon)).miles
                    if max_proximity_miles > 0 and dist > max_proximity_miles:
                        logger.info(f"Reached max proximity ({dist:.2f} > {max_proximity_miles} miles). Stopping.")
                        break
                
                logger.info(f"Processing location: {lat:.4f}, {lon:.4f} (Dist: {dist:.1f} mi)")
                
                # Reset bandwidth tracker for this location to see per-task usage
                start_mb = self.bandwidth_tracker.get_mb() if self.bandwidth_tracker else 0.0
                
                # 2. Determine Scope (Expand-Out)
                # We attempt to define the largest effective box for this center point
                # For now, simplistic approach: Use base size. 
                
                current_width = self.base_width_miles
                current_height = self.base_height_miles
                
                # Check if this area is already covered
                bounds = get_viewport_bounds(lat, lon, current_width, current_height)
                
                # Scrape each query
                for query in search_phrases:
                    # In Grid Mode (tile_id present), we bypass the wilderness/overlap check
                    # to strictly follow the grid plan.
                    if not tile_id and not self.wilderness.should_scrape(bounds, query):
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
                    async for item in scanner.scrape(query, processed_ids, force_refresh, ttl_days, tile_id=tile_id):
                        yield item
                        items_found += 1
                        
                    # Mark Index
                    self.wilderness.mark_scraped(bounds, query, items_found, record_width, record_height, tile_id=tile_id, processed_by=processed_by)
                
                # Log bandwidth usage for this location
                end_mb = self.bandwidth_tracker.get_mb() if self.bandwidth_tracker else 0.0
                logger.info(f"Bandwidth used for location: {end_mb - start_mb:.2f} MB (Total: {end_mb:.2f} MB)")
                    
        finally:
            await context.close()
