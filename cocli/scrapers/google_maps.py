import re
from typing import Optional, Dict, List, AsyncIterator
from datetime import datetime, timedelta, UTC
from playwright.async_api import Page, Browser
import logging
from rich.console import Console
from geopy.distance import geodesic # type: ignore

from ..core.config import load_scraper_settings
from ..core.geocoding import get_coordinates_from_zip, get_coordinates_from_city_state
from .google_maps_parser import parse_business_listing_html
from .google_maps_gmb_parser import parse_gmb_page
from ..models.google_maps import GoogleMapsData
from ..core.google_maps_cache import GoogleMapsCache
from ..core.scrape_index import ScrapeIndex

logger = logging.getLogger(__name__)
console = Console()

def calculate_new_coords(lat: float, lon: float, distance_miles: float, bearing: float) -> tuple[float, float]:
    """Calculate new lat/lon from a starting point, distance, and bearing."""
    start_point = (lat, lon)
    distance_km = distance_miles * 1.60934
    destination = geodesic(kilometers=distance_km).destination(start_point, bearing)
    return destination.latitude, destination.longitude

def get_viewport_bounds(center_lat: float, center_lon: float, map_width_miles: float, map_height_miles: float, margin: float = 0.1) -> dict[str, float]:
    """
    Calculates the bounding box of the map viewport, inset by a margin.
    A margin of 0.1 means the box is 10% smaller on each side (80% of original area).
    """
    effective_width_miles = map_width_miles * (1 - 2 * margin)
    effective_height_miles = map_height_miles * (1 - 2 * margin)

    half_width = effective_width_miles / 2
    half_height = effective_height_miles / 2

    lat_max, _ = calculate_new_coords(center_lat, center_lon, half_height, 0)  # North
    lat_min, _ = calculate_new_coords(center_lat, center_lon, half_height, 180) # South

    # For longitude, calculate from the center latitude for better accuracy
    _, lon_max = calculate_new_coords(center_lat, center_lon, half_width, 90)  # East
    _, lon_min = calculate_new_coords(center_lat, center_lon, half_width, 270) # West

    return {
        'lat_min': lat_min,
        'lat_max': lat_max,
        'lon_min': lon_min,
        'lon_max': lon_max,
    }

async def _scrape_area(
    page: Page,
    search_string: str,
    processed_place_ids: set[str],
    force_refresh: bool,
    ttl_days: int,
    debug: bool,
) -> AsyncIterator[GoogleMapsData]:
    """
    Helper function to scrape a specific map area for a single search query.
    This function contains the core logic for scrolling, parsing, and yielding results.
    """
    settings = load_scraper_settings()
    delay_seconds = settings.google_maps_delay_seconds
    cache = GoogleMapsCache()
    fresh_delta = timedelta(days=ttl_days)

    logger.info(f"--- Starting search for query: '{search_string}' ---")
    search_box_selector = 'input[name="q"]'
    await page.wait_for_selector(search_box_selector)
    await page.fill(search_box_selector, search_string)
    await page.press(search_box_selector, 'Enter')
    await page.wait_for_timeout(5000)

    scrollable_div_selector = 'div[role="feed"]'
    await page.wait_for_selector(scrollable_div_selector, timeout=10000)
    scrollable_div = page.locator(scrollable_div_selector)

    _ = -1
    last_processed_div_count = 0
    while True:
        await page.wait_for_timeout(1500)
        listing_divs = await scrollable_div.locator("> div").all()
        logger.debug(f"[SCROLL_DEBUG] Found {len(listing_divs)} listing divs before scroll. last_processed_div_count: {last_processed_div_count}")

        if debug:
            page_source = await page.content()
            with open(f"page_source_before_scroll_{search_string.replace(' ', '_')}.html", "w") as f:
                f.write(page_source)

        if not listing_divs or len(listing_divs) == last_processed_div_count:
            logger.debug("No new listing divs found. Moving to next query.")
            break

        # Only process the new divs that have appeared since the last scroll
        for i in range(last_processed_div_count, len(listing_divs)):
            listing_div = listing_divs[i]
            html_content = ""
            try:
                # Set a shorter timeout for getting the HTML of a single element
                html_content = await listing_div.inner_html(timeout=5000)
            except Exception:
                logger.warning(f"Skipping unloaded listing div {i} for query '{search_string}' (timeout).")
                continue
            if not html_content or "All filters" in html_content or "Prices come from Google" in html_content:
                continue

            business_data_dict = {}
            try:
                business_data_dict = parse_business_listing_html(html_content, search_string, debug=debug)
            except IndexError as e:
                logger.error(f"IndexError during parsing for search_string '{search_string}'. HTML content: {html_content[:500]}... Error: {e}", exc_info=True)
                continue
            except Exception as e:
                logger.error(f"Unexpected error during parsing for search_string '{search_string}'. HTML content: {html_content[:500]}... Error: {e}", exc_info=True)
                continue
            
            place_id = business_data_dict.get("Place_ID")

            logger.debug(f"Checking place_id: {place_id}")
            logger.debug(f"processed_place_ids: {processed_place_ids}")

            if not place_id or place_id in processed_place_ids:
                logger.debug(f"Skipping duplicate place_id: {place_id}")
                continue
            
            processed_place_ids.add(place_id)

            cached_item = cache.get_by_place_id(place_id)
            if cached_item and not force_refresh and (datetime.now(UTC) - cached_item.updated_at < fresh_delta):
                logger.debug(f"Yielding cached data for: {cached_item.Name}")
                yield cached_item
                continue

            gmb_url = business_data_dict.get("GMB_URL")
            if gmb_url and (not business_data_dict.get("Website") or not business_data_dict.get("Full_Address")):
                try:
                    browser = page.context.browser
                    if browser:
                        context = await browser.new_context()
                        gmb_page = await context.new_page()
                        try:
                            await gmb_page.goto(gmb_url)
                            gmb_html = await gmb_page.content()
                            gmb_data = parse_gmb_page(gmb_html)
                            business_data_dict.update(gmb_data)
                        finally:
                            await context.close() # Closes the context and all its pages
                    else:
                        # This should not happen in a normal run
                        raise Exception("Browser object not available from page context.")
                except Exception as gmb_e:
                    logger.warning(f"Failed to scrape GMB page {gmb_url}: {gmb_e}")

            business_data = GoogleMapsData(**business_data_dict)
            cache.add_or_update(business_data)
            logger.info(f"Yielding new record: {business_data.Name}")
            yield business_data

        last_processed_div_count = len(listing_divs)

        # Check for the end of the list message
        end_of_list_text = "You've reached the end of the list."
        if await page.get_by_text(end_of_list_text).is_visible():
            logger.debug(f"'{end_of_list_text}' message visible. Reached end of content for '{search_string}'.")
            break

        # Scroll down to trigger loading of more results
        await scrollable_div.hover()
        await page.mouse.wheel(0, 10000) # Scroll down by a large amount
        logger.debug("[SCROLL_DEBUG]   ...scrolled. Waiting for content to load.")
        await page.wait_for_timeout(delay_seconds * 1000)

        if debug:
            page_source = await page.content()
            with open(f"page_source_after_scroll_{search_string.replace(' ', '_')}.html", "w") as f:
                f.write(page_source)

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
    max_proximity_miles: float = 0.0, # 0.0 means unlimited (or constrained by other factors)
    overlap_threshold_percent: float = 30.0, # New parameter
) -> AsyncIterator[GoogleMapsData]:
    """
    Scrapes business information from Google Maps for a list of search queries,
    yielding each result as it is found.
    
    Uses a pre-existing browser instance.
    """
    if debug:
        logger.debug(f"scrape_google_maps called with debug={debug}")
    settings = load_scraper_settings()
    scrape_index = ScrapeIndex()

    launch_width = browser_width if browser_width is not None else settings.browser_width
    launch_height = browser_height if browser_height is not None else settings.browser_height

    if "latitude" in location_param and "longitude" in location_param:
        latitude = float(location_param["latitude"])
        longitude = float(location_param["longitude"])
        logger.info(f"Using explicit coordinates: {latitude}, {longitude}")
    else:
        coordinates = get_coordinates_from_city_state(location_param["city"]) if "city" in location_param else get_coordinates_from_zip(location_param["zip_code"])

        if not coordinates:
            logger.error(f"Error: Could not find coordinates for {location_param}")
            return

        latitude = coordinates["latitude"]
        longitude = coordinates["longitude"]
        
    start_lat, start_lon = latitude, longitude # Remember starting point for proximity check
    
    processed_place_ids: set[str] = set()

    page = await browser.new_page(viewport={'width': launch_width, 'height': launch_height})
    try:
        initial_url = f"https://www.google.com/maps/@{latitude},{longitude},15z?entry=ttu"
        await page.goto(initial_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        logger.info(f"Navigated to initial map URL for {location_param}.")

        # Handle Cookie Consent
        try:
            reject_button = page.get_by_role("button", name=re.compile("Reject all", re.IGNORECASE))
            if await reject_button.is_visible():
                logger.info("Cookie consent dialog found. Clicking 'Reject all'.")
                await reject_button.click()
                await page.wait_for_timeout(2000) # Wait for the dialog to disappear
        except Exception as e:
            logger.info(f"Could not find or click cookie consent button (this is okay if it's not present): {e}")

        if not omit_zoom_feature and initial_zoom_out_level > 0:
            await page.wait_for_selector(zoom_out_button_selector, timeout=10000)
            for i in range(initial_zoom_out_level):
                await page.click(zoom_out_button_selector)
                await page.wait_for_timeout(500)
            logger.info(f"Zoomed out {initial_zoom_out_level} times.")
            await page.wait_for_timeout(5000)

        map_width_miles: float = 0.0
        map_height_miles: float = 0.0
        px_per_mile: float = 0.0
        try:
            scale_button = page.locator("button[jsaction=\"scale.click\"]")
            scale_label = await scale_button.text_content()
            scale_inner_div = scale_button.locator("div").first
            style = await scale_inner_div.get_attribute("style")
            width_match: Optional[re.Match[str]] = None # Initialize to None
            if style:
                width_match = re.search(r'width:\s*(\d+)px;', style)
            if width_match and scale_label:
                width_px = int(width_match.group(1))
                # Extract the number and unit from the scale label (e.g., "2 mi" -> 2, "mi")
                scale_number_match = re.search(r'(\d+)', scale_label)
                if scale_number_match:
                    scale_number = int(scale_number_match.group(1))
                    # Calculate pixels per mile
                    if "mi" in scale_label:
                        px_per_mile = width_px / scale_number
                    elif "km" in scale_label:
                        px_per_mile = width_px / (scale_number * 0.621371)
                    else: # assume feet
                        px_per_mile = width_px / (scale_number / 5280)
                    
                    if px_per_mile > 0:
                        map_width_miles = launch_width / px_per_mile
                        map_height_miles = launch_height / px_per_mile
                        logger.info(f"Map scale: {scale_label} = {width_px}px. Estimated map width: {map_width_miles:.2f} miles.")
        except Exception as e:
            logger.warning(f"Could not extract map scale: {e}")

        # Initial scrape of the main area
        for search_string in search_strings:
            # Calculate viewport bounds for the current location
            current_viewport_bounds = get_viewport_bounds(latitude, longitude, map_width_miles, map_height_miles)

            # Check if area is already known wilderness
            if scrape_index.is_wilderness_area(current_viewport_bounds, overlap_threshold_percent):
                logger.info(f"Skipping initial area ({latitude:.4f}, {longitude:.4f}) as it falls within a known wilderness area.")
                continue

            matched_area = scrape_index.is_area_scraped(search_string, current_viewport_bounds, ttl_days=ttl_days, overlap_threshold_percent=overlap_threshold_percent)
            if matched_area:
                logger.info(f"Skipping initial area for phrase '{search_string}' as it falls within a recently scraped box ({matched_area.lat_min:.4f}, {matched_area.lon_min:.4f} to {matched_area.lat_max:.4f}, {matched_area.lon_max:.4f}).")
                continue
    
            items_found_in_area = 0
            async for item in _scrape_area(
                page=page,
                search_string=search_string,
                processed_place_ids=processed_place_ids,
                force_refresh=force_refresh,
                ttl_days=ttl_days,
                debug=debug,
            ):
                items_found_in_area += 1
                yield item
            
            if items_found_in_area > 0 and map_width_miles > 0:
                viewport_bounds = get_viewport_bounds(latitude, longitude, map_width_miles, map_height_miles)
                # Round values for cleaner CSV
                for k, v in viewport_bounds.items():
                    viewport_bounds[k] = round(v, 5)
                scrape_index.add_area(search_string, viewport_bounds, lat_miles=round(map_height_miles, 3), lon_miles=round(map_width_miles, 3), items_found=items_found_in_area)
                logger.info(f"Added viewport-based bounding box to scrape index for phrase '{search_string}'. Items found: {items_found_in_area}")
            elif map_width_miles > 0: # items_found_in_area is 0
                viewport_bounds = get_viewport_bounds(latitude, longitude, map_width_miles, map_height_miles)
                for k, v in viewport_bounds.items():
                    viewport_bounds[k] = round(v, 5)
                scrape_index.add_wilderness_area(viewport_bounds, lat_miles=round(map_height_miles, 3), lon_miles=round(map_width_miles, 3), items_found=0)
                logger.info(f"No items found in initial area for phrase '{search_string}'. Marked as wilderness.")
    
        if disable_panning:
            logger.info("Panning is disabled. Finishing scrape for this location.")
            return
    
        # Start of spiral out logic
        logger.info("Starting spiral out search...")
        current_lat, current_lon = latitude, longitude
        distance_miles = panning_distance_miles
        
        bearings = [0, 90, 180, 270] # N, E, S, W
        steps_in_direction = 1
        leg_count = 0
        direction_index = 0
    
        while True: # This loop will run until the consumer (scrape_prospects) stops it
            for _ in range(steps_in_direction):
                # Calculate new coordinates
                bearing = bearings[direction_index]
                current_lat, current_lon = calculate_new_coords(current_lat, current_lon, distance_miles, bearing)
                
                # Check Proximity limit
                if max_proximity_miles > 0:
                    dist_from_start = geodesic((start_lat, start_lon), (current_lat, current_lon)).miles
                    if dist_from_start > max_proximity_miles:
                        console.print(f"[yellow]Reached max proximity ({dist_from_start:.2f} > {max_proximity_miles} miles). Stopping scrape for this location.[/yellow]")
                        return
    
                direction_name = ['North', 'East', 'South', 'West'][direction_index]
                console.print(f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [bold yellow]Moving {distance_miles} miles {direction_name} to {current_lat:.4f}, {current_lon:.4f}...[/bold yellow]")
                
                # Navigate to new coordinates
                new_url = f"https://www.google.com/maps/@{current_lat},{current_lon},15z?entry=ttu"
                await page.goto(new_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(5000) # Wait for map to settle

                # Click "Search this area"
                try:
                    search_this_area_button = page.get_by_role("button", name=re.compile("Search this area", re.IGNORECASE))
                    if await search_this_area_button.is_visible():
                        logger.info("'Search this area' button found. Clicking...")
                        await search_this_area_button.click()
                        await page.wait_for_timeout(5000) # Wait for results to load
                    else:
                        logger.debug("'Search this area' button not visible.")
                except Exception:
                    logger.debug("'Search this area' button not found.")

                # Scrape the new area for each search string
                for search_string in search_strings:
                    # Calculate viewport bounds for the current location
                    current_viewport_bounds = get_viewport_bounds(current_lat, current_lon, map_width_miles, map_height_miles)

                    # Check if area is already known wilderness
                    if scrape_index.is_wilderness_area(current_viewport_bounds, overlap_threshold_percent):
                        logger.info(f"Skipping area ({current_lat:.4f}, {current_lon:.4f}) as it falls within a known wilderness area.")
                        continue

                    matched_area = scrape_index.is_area_scraped(search_string, current_viewport_bounds, ttl_days=ttl_days, overlap_threshold_percent=overlap_threshold_percent)
                    if matched_area:
                        logger.info(f"Skipping area for phrase '{search_string}' as it falls within a recently scraped box ({matched_area.lat_min:.4f}, {matched_area.lon_min:.4f} to {matched_area.lat_max:.4f}, {matched_area.lon_max:.4f}).")
                        continue

                    items_found_in_area = 0
                    async for item in _scrape_area(
                        page=page,
                        search_string=search_string,
                        processed_place_ids=processed_place_ids,
                        force_refresh=force_refresh,
                        ttl_days=ttl_days,
                        debug=debug,
                    ):
                        items_found_in_area += 1
                        yield item

                    if items_found_in_area > 0 and map_width_miles > 0:
                        viewport_bounds = get_viewport_bounds(current_lat, current_lon, map_width_miles, map_height_miles)
                        scrape_index.add_area(search_string, viewport_bounds, lat_miles=map_height_miles, lon_miles=map_width_miles, items_found=items_found_in_area)
                        logger.info(f"Added viewport-based bounding box to scrape index for phrase '{search_string}'. Items found: {items_found_in_area}")
                    elif map_width_miles > 0: # items_found_in_area is 0
                        viewport_bounds = get_viewport_bounds(current_lat, current_lon, map_width_miles, map_height_miles)
                        for k, v in viewport_bounds.items():
                            viewport_bounds[k] = round(v, 5)
                        scrape_index.add_wilderness_area(viewport_bounds, lat_miles=map_height_miles, lon_miles=map_width_miles, items_found=0)
                        logger.info(f"No items found in area for phrase '{search_string}'. Marked as wilderness.")

                # Update spiral direction and steps
                leg_count += 1
                if leg_count % 2 == 0:
                    steps_in_direction += 1
                direction_index = (direction_index + 1) % 4

    except Exception as e:
        logger.error(f"An error occurred during scraping: {e}")
    finally:
        GoogleMapsCache().save()
        await page.close()
