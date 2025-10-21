import csv
import re
from pathlib import Path
from typing import Optional, Dict, Any, List, AsyncIterator
from datetime import datetime, timedelta, UTC
from playwright.async_api import async_playwright, Page, Locator
from bs4 import BeautifulSoup
import uuid
import logging
from rich.console import Console
from geopy.distance import geodesic # type: ignore

def calculate_new_coords(lat, lon, distance_miles, bearing):
    """Calculate new lat/lon from a starting point, distance, and bearing."""
    start_point = (lat, lon)
    distance_km = distance_miles * 1.60934
    destination = geodesic(kilometers=distance_km).destination(start_point, bearing)
    return destination.latitude, destination.longitude

from ..core.config import load_scraper_settings
from ..core.geocoding import get_coordinates_from_zip, get_coordinates_from_city_state
from .google_maps_parser import parse_business_listing_html
from .google_maps_gmb_parser import parse_gmb_page
from ..models.google_maps import GoogleMapsData
from ..core.google_maps_cache import GoogleMapsCache

logger = logging.getLogger(__name__)
console = Console()

from ..core.scrape_index import ScrapeIndex

async def _scrape_area(
    page: Page,
    search_string: str, # Changed from search_strings
    processed_place_ids: set,
    scrape_index: ScrapeIndex, # Added scrape_index
    force_refresh: bool,
    ttl_days: int,
    debug: bool,
) -> AsyncIterator[GoogleMapsData]:
    """
    Helper function to scrape a specific map area for a single search query.
    This function contains the core logic for scrolling, parsing, and yielding results.
    It now also records the bounding box of found results to the scrape_index.
    """
    settings = load_scraper_settings()
    delay_seconds = settings.google_maps_delay_seconds
    cache = GoogleMapsCache()
    fresh_delta = timedelta(days=ttl_days)
    found_coords = []

    logger.info(f"--- Starting search for query: '{search_string}' ---")
    search_box_selector = 'input[name="q"]'
    await page.wait_for_selector(search_box_selector)
    await page.fill(search_box_selector, search_string)
    await page.press(search_box_selector, 'Enter')
    await page.wait_for_timeout(5000)

    scrollable_div_selector = 'div[role="feed"]'
    await page.wait_for_selector(scrollable_div_selector, timeout=10000)
    scrollable_div = page.locator(scrollable_div_selector)

    last_scroll_height = -1
    last_processed_div_count = 0
    while True:
        await page.wait_for_timeout(1500)
        listing_divs = await scrollable_div.locator("> div").all()
        logger.info(f"[SCROLL_DEBUG] Found {len(listing_divs)} listing divs before scroll. last_processed_div_count: {last_processed_div_count}")

        if debug:
            page_source = await page.content()
            with open(f"page_source_before_scroll_{search_string.replace(' ', '_')}.html", "w") as f:
                f.write(page_source)

        if not listing_divs or len(listing_divs) == last_processed_div_count:
            logger.info("No new listing divs found. Moving to next query.")
            break

        # Only process the new divs that have appeared since the last scroll
        for i in range(last_processed_div_count, len(listing_divs)):
            listing_div = listing_divs[i]
            html_content = ""
            try:
                # Set a shorter timeout for getting the HTML of a single element
                html_content = await listing_div.inner_html(timeout=5000)
            except Exception as e:
                logger.warning(f"Could not get HTML for a listing div, it might have been unloaded. Skipping. Error: {e}")
                continue
            if not html_content or "All filters" in html_content or "Prices come from Google" in html_content:
                continue

            business_data_dict = parse_business_listing_html(html_content, search_string, debug=debug)
            place_id = business_data_dict.get("Place_ID")

            logger.info(f"Checking place_id: {place_id}")
            logger.info(f"processed_place_ids: {processed_place_ids}")

            if not place_id or place_id in processed_place_ids:
                logger.info(f"Skipping duplicate place_id: {place_id}")
                continue
            
            processed_place_ids.add(place_id)

            cached_item = cache.get_by_place_id(place_id)
            if cached_item and not force_refresh and (datetime.now(UTC) - cached_item.updated_at < fresh_delta):
                logger.info(f"Yielding cached data for: {cached_item.Name}")
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
            if business_data.Latitude and business_data.Longitude:
                found_coords.append((business_data.Latitude, business_data.Longitude))
            yield business_data

        last_processed_div_count = len(listing_divs)

        # Check for the end of the list message
        end_of_list_text = "You've reached the end of the list."
        if await page.get_by_text(end_of_list_text).is_visible():
            logger.info(f"'{end_of_list_text}' message visible. Reached end of content for '{search_string}'.")
            break

        # Scroll down to trigger loading of more results
        await scrollable_div.hover()
        await page.mouse.wheel(0, 10000) # Scroll down by a large amount
        logger.info("[SCROLL_DEBUG]   ...scrolled. Waiting for content to load.")
        await page.wait_for_timeout(delay_seconds * 1000)

        if debug:
            page_source = await page.content()
            with open(f"page_source_after_scroll_{search_string.replace(' ', '_')}.html", "w") as f:
                f.write(page_source)

    # After finishing the scrape for this area, calculate bounds and save to index
    if found_coords:
        lats, lons = zip(*found_coords)
        bounds = {
            'lat_min': min(lats),
            'lat_max': max(lats),
            'lon_min': min(lons),
            'lon_max': max(lons),
        }
        scrape_index.add_area(search_string, bounds)
        logger.info(f"Added bounding box to scrape index for phrase '{search_string}'.")

from playwright.async_api import async_playwright, Page, Locator, Browser

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
    zoom_out_level: int = 0,
) -> AsyncIterator[GoogleMapsData]:
    """
    Scrapes business information from Google Maps for a list of search queries,
    yielding each result as it is found.
    
    Uses a pre-existing browser instance.
    """
    if debug: logger.debug(f"scrape_google_maps called with debug={debug}")
    settings = load_scraper_settings()
    scrape_index = ScrapeIndex(campaign_name)

    launch_width = browser_width if browser_width is not None else settings.browser_width
    launch_height = browser_height if browser_height is not None else settings.browser_height

    coordinates = get_coordinates_from_city_state(location_param["city"]) if "city" in location_param else get_coordinates_from_zip(location_param["zip_code"])

    if not coordinates:
        logger.error(f"Error: Could not find coordinates for {location_param}")
        return

    latitude = coordinates["latitude"]
    longitude = coordinates["longitude"]
    
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

        if zoom_out_level > 0:
            zoom_out_button_selector = "button#widget-zoom-out"
            await page.wait_for_selector(zoom_out_button_selector, timeout=10000)
            for i in range(zoom_out_level):
                await page.click(zoom_out_button_selector)
                await page.wait_for_timeout(500)
            logger.info(f"Zoomed out {zoom_out_level} times.")
            await page.wait_for_timeout(5000)

        try:
            scale_button = page.locator('button[jsaction="scale.click"]')
            scale_label = await scale_button.text_content()
            scale_inner_div = scale_button.locator('div').first
            style = await scale_inner_div.get_attribute('style')
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
                        logger.info(f"Map scale: {scale_label} = {width_px}px. Estimated map width: {map_width_miles:.2f} miles.")
        except Exception as e:
            logger.warning(f"Could not extract map scale: {e}")

        # Initial scrape of the main area
        for search_string in search_strings:
            matched_area = scrape_index.is_area_scraped(search_string, latitude, longitude, ttl_days=ttl_days)
            if matched_area:
                logger.info(f"Skipping initial area for phrase '{search_string}' as it falls within a recently scraped box ({matched_area.lat_min:.4f}, {matched_area.lon_min:.4f} to {matched_area.lat_max:.4f}, {matched_area.lon_max:.4f}).")
                continue

            async for item in _scrape_area(
                page=page,
                search_string=search_string,
                processed_place_ids=processed_place_ids,
                scrape_index=scrape_index,
                force_refresh=force_refresh,
                ttl_days=ttl_days,
                debug=debug,
            ):
                yield item

        # Start of spiral out logic
        logger.info("Starting spiral out search...")
        current_lat, current_lon = latitude, longitude
        distance_miles = 8
        
        bearings = [0, 90, 180, 270] # N, E, S, W
        steps_in_direction = 1
        leg_count = 0
        direction_index = 0

        while True: # This loop will run until the consumer (scrape_prospects) stops it
            for _ in range(steps_in_direction):
                # Calculate new coordinates
                bearing = bearings[direction_index]
                current_lat, current_lon = calculate_new_coords(current_lat, current_lon, distance_miles, bearing)
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
                        logger.info("'Search this area' button not visible.")
                except Exception:
                    logger.info("'Search this area' button not found.")

                # Scrape the new area for each search string
                for search_string in search_strings:
                    matched_area = scrape_index.is_area_scraped(search_string, current_lat, current_lon, ttl_days=ttl_days)
                    if matched_area:
                        logger.info(f"Skipping area for phrase '{search_string}' as it falls within a recently scraped box ({matched_area.lat_min:.4f}, {matched_area.lon_min:.4f} to {matched_area.lat_max:.4f}, {matched_area.lon_max:.4f}).")
                        continue

                    async for item in _scrape_area(
                        page=page,
                        search_string=search_string,
                        processed_place_ids=processed_place_ids,
                        scrape_index=scrape_index,
                        force_refresh=force_refresh,
                        ttl_days=ttl_days,
                        debug=debug,
                    ):
                        yield item

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