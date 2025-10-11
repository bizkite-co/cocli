
import csv
import re
from pathlib import Path
from typing import Optional, Dict, Any, List, Iterator
from datetime import datetime, timedelta, UTC
from playwright.sync_api import sync_playwright, Page, Locator
from bs4 import BeautifulSoup
import uuid
import logging
from rich.console import Console

from ..core.config import load_scraper_settings
from ..core.geocoding import get_coordinates_from_zip, get_coordinates_from_city_state
from .google_maps_parser import parse_business_listing_html
from .google_maps_gmb_parser import parse_gmb_page
from ..models.google_maps import GoogleMapsData
from ..core.google_maps_cache import GoogleMapsCache

logger = logging.getLogger(__name__)
console = Console()

def scrape_google_maps(
    location_param: Dict[str, str],
    search_strings: List[str],
    debug: bool = False,
    force_refresh: bool = False,
    ttl_days: int = 30,
    headless: Optional[bool] = None,
    browser_width: Optional[int] = None,
    browser_height: Optional[int] = None,
    devtools: Optional[bool] = None,
    zoom_out_level: int = 0,
) -> Iterator[GoogleMapsData]:
    """
    Scrapes business information from Google Maps for a list of search queries,
    yielding each result as it is found.
    """
    if debug: logger.debug(f"scrape_google_maps called with debug={debug}")
    settings = load_scraper_settings()
    delay_seconds = settings.google_maps_delay_seconds

    launch_headless = headless if headless is not None else settings.browser_headless
    launch_width = browser_width if browser_width is not None else settings.browser_width
    launch_height = browser_height if browser_height is not None else settings.browser_height
    launch_devtools = devtools if devtools is not None else settings.browser_devtools

    cache = GoogleMapsCache()
    fresh_delta = timedelta(days=ttl_days)

    coordinates = get_coordinates_from_city_state(location_param["city"]) if "city" in location_param else get_coordinates_from_zip(location_param["zip_code"])

    if not coordinates:
        logger.error(f"Error: Could not find coordinates for {location_param}")
        return

    latitude = coordinates["latitude"]
    longitude = coordinates["longitude"]
    
    processed_place_ids = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=launch_headless,
            devtools=launch_devtools,
            args=[f'--window-size={launch_width},{launch_height}']
        )
        page = browser.new_page(viewport={'width': launch_width, 'height': launch_height})

        try:
            initial_url = f"https://www.google.com/maps/@{latitude},{longitude},15z?entry=ttu"
            page.goto(initial_url, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            logger.info(f"Navigated to initial map URL for {location_param}.")

            # Handle Cookie Consent
            try:
                reject_button = page.get_by_role("button", name=re.compile("Reject all", re.IGNORECASE))
                if reject_button.is_visible():
                    logger.info("Cookie consent dialog found. Clicking 'Reject all'.")
                    reject_button.click()
                    page.wait_for_timeout(2000) # Wait for the dialog to disappear
            except Exception as e:
                logger.info(f"Could not find or click cookie consent button (this is okay if it's not present): {e}")

            if zoom_out_level > 0:
                zoom_out_button_selector = "button#widget-zoom-out"
                page.wait_for_selector(zoom_out_button_selector, timeout=10000)
                for i in range(zoom_out_level):
                    page.click(zoom_out_button_selector)
                    page.wait_for_timeout(500)
                logger.info(f"Zoomed out {zoom_out_level} times.")
                page.wait_for_timeout(5000)

            for search_string in search_strings:
                logger.info(f"--- Starting search for query: '{search_string}' ---")
                search_box_selector = 'input[name="q"]'
                page.wait_for_selector(search_box_selector)
                page.fill(search_box_selector, search_string)
                page.press(search_box_selector, 'Enter')
                page.wait_for_timeout(5000)

                scrollable_div_selector = 'div[role="feed"]'
                page.wait_for_selector(scrollable_div_selector, timeout=10000)
                scrollable_div = page.locator(scrollable_div_selector)

                last_scroll_height = -1
                while True:
                    # Pre-scroll logging
                    page.wait_for_timeout(1500)
                    listing_divs = scrollable_div.locator("> div").all()
                    logger.info(f"[SCROLL_DEBUG] Found {len(listing_divs)} listing divs before scroll.")
                    try:
                        if listing_divs:
                            first_item_text = ' '.join(listing_divs[0].inner_text().splitlines())[:70]
                            last_item_text = ' '.join(listing_divs[-1].inner_text().splitlines())[:70]
                            logger.info(f"[SCROLL_DEBUG]   Pre-scroll First: {first_item_text}...")
                            logger.info(f"[SCROLL_DEBUG]   Pre-scroll Last:  {last_item_text}...")
                    except Exception as e:
                        logger.warning(f"[SCROLL_DEBUG] Could not read pre-scroll item text: {e}")

                    if not listing_divs:
                        logger.info("No listing divs found. Moving to next query.")
                        break

                    for listing_div in listing_divs:
                        html_content = listing_div.inner_html()
                        if not html_content or "All filters" in html_content or "Prices come from Google" in html_content:
                            continue

                        business_data_dict = parse_business_listing_html(html_content, search_string, debug=debug)
                        place_id = business_data_dict.get("Place_ID")

                        if not place_id or place_id in processed_place_ids:
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
                                gmb_page = browser.new_page()
                                gmb_page.goto(gmb_url)
                                gmb_html = gmb_page.content()
                                gmb_data = parse_gmb_page(gmb_html)
                                business_data_dict.update(gmb_data)
                                gmb_page.close()
                            except Exception as gmb_e:
                                logger.warning(f"Failed to scrape GMB page {gmb_url}: {gmb_e}")

                        business_data = GoogleMapsData(**business_data_dict)
                        cache.add_or_update(business_data)
                        logger.info(f"Yielding new record: {business_data.Name}")
                        yield business_data

                    # Scroll logic and post-scroll logging
                    logger.info("[SCROLL_DEBUG] Attempting to scroll...")
                    current_scroll_height = scrollable_div.evaluate("element => element.scrollHeight")
                    logger.info(f"[SCROLL_DEBUG]   Scroll height before scroll action: {current_scroll_height}")

                    if current_scroll_height == last_scroll_height:
                        logger.info(f"[SCROLL_DEBUG] Scroll height hasn't changed. Reached end of content for '{search_string}'.")
                        console.print(f"[yellow] scraper: Reached end of results for query: '{search_string}'[/yellow]")
                        break

                    scrollable_div.evaluate("element => element.scrollTop = element.scrollHeight")
                    last_scroll_height = current_scroll_height
                    logger.info("[SCROLL_DEBUG]   ...scrolled. Waiting for content to load.")
                    page.wait_for_timeout(delay_seconds * 1000)

        except Exception as e:
            logger.error(f"An error occurred during scraping: {e}")
        finally:
            cache.save()
            browser.close()
