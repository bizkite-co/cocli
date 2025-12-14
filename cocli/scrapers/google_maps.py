import logging
from typing import AsyncIterator, Dict, List, Optional, Any
from playwright.async_api import Browser

from .gm_scraper.coordinator import ScrapeCoordinator
from ..models.google_maps_prospect import GoogleMapsProspect
from ..core.config import load_scraper_settings # Added import

logger = logging.getLogger(__name__)

async def scrape_google_maps(
    browser: Browser,
    location_param: Dict[str, str],
    search_strings: List[str],
    campaign_name: str,
    debug: bool = False,
    force_refresh: bool = False,
    ttl_days: int = 30,
    browser_width: Optional[int] = None,
    browser_height: Optional[int] = None,
    zoom_out_button_selector: str = "div#zoomOutButton",
    panning_distance_miles: int = 8,
    initial_zoom_out_level: int = 3,
    omit_zoom_feature: bool = False,
    disable_panning: bool = False,
    max_proximity_miles: float = 0.0,
    overlap_threshold_percent: float = 60.0,
    expansion_factor: float = 1.0,
    max_initial_expansion_attempts: int = 3,
    grid_tiles: Optional[List[Dict[str, Any]]] = None,
) -> AsyncIterator[GoogleMapsProspect]:
    """
    Scrapes business information from Google Maps using the modular ScrapeCoordinator.
    Maintains compatibility with the legacy signature.
    """
    settings = load_scraper_settings()

    launch_width = browser_width if browser_width is not None else settings.browser_width
    launch_height = browser_height if browser_height is not None else settings.browser_height

    logger.info("Using modular ScrapeCoordinator for Google Maps scraping.")
    
    # Resolve coordinates
    # We leave this resolution logic here or move it? 
    # Coordinator expects lat/lon. Let's resolve here to keep Coordinator clean.
    from ..core.geocoding import get_coordinates_from_zip, get_coordinates_from_city_state
    
    latitude = 0.0
    longitude = 0.0
    
    if "latitude" in location_param and "longitude" in location_param:
        latitude = float(location_param["latitude"])
        longitude = float(location_param["longitude"])
    else:
        coordinates = None
        if "city" in location_param:
            coordinates = get_coordinates_from_city_state(location_param["city"])
        elif "zip_code" in location_param:
            coordinates = get_coordinates_from_zip(location_param["zip_code"])
            
        if coordinates:
            latitude = coordinates["latitude"]
            longitude = coordinates["longitude"]
        else:
            logger.error(f"Could not resolve coordinates for {location_param}")
            return

    # Initialize Coordinator
    # We approximate the base width/height for standard 15z view
    # 15z is roughly 1-2 miles wide depending on lat. 
    # Let's start with a conservative 2.0 miles width.
    # If grid_tiles are provided (Grid Mode), we need to cover a 0.1 degree tile (approx 7 miles).
    # We set base dimensions to 8.0 miles to ensure full coverage with some margin.
    base_w = 8.0 if grid_tiles else 5.0
    base_h = 8.0 if grid_tiles else 5.0

    coordinator = ScrapeCoordinator(
        browser=browser,
        campaign_name=campaign_name,
        base_width_miles=base_w,
        base_height_miles=base_h,
        viewport_width=launch_width,
        viewport_height=launch_height,
        debug=debug
    )
    
    # Run
    async for item in coordinator.run(
        start_lat=latitude,
        start_lon=longitude,
        search_phrases=search_strings,
        max_proximity_miles=max_proximity_miles,
        panning_distance_miles=panning_distance_miles,
        force_refresh=force_refresh,
        ttl_days=ttl_days,
        grid_tiles=grid_tiles
    ):
        yield item

