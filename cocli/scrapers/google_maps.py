
import csv
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, Page, Locator
from bs4 import BeautifulSoup
import uuid

from ..core.config import load_scraper_settings
from ..core.geocoding import get_coordinates_from_zip, get_coordinates_from_city_state
from .google_maps_parser import parse_business_listing_html
from .google_maps_gmb_parser import parse_gmb_page
from ..models.google_maps import GoogleMapsData
from ..core.google_maps_cache import GoogleMapsCache

def scrape_google_maps(
    location_param: Dict[str, str],
    search_string: str,
    max_results: int = 30,
    debug: bool = False,
    force_refresh: bool = False,
    ttl_days: int = 30,
    headless: Optional[bool] = None,
    browser_width: Optional[int] = None,
    browser_height: Optional[int] = None,
    devtools: Optional[bool] = None,
) -> List[GoogleMapsData]:
    """
    Scrapes business information from Google Maps, using a cache-first strategy.
    """
    if debug: print(f"Debug: scrape_google_maps called with debug={debug}")
    settings = load_scraper_settings()
    delay_seconds = settings.google_maps_delay_seconds

    # Override global settings with function arguments if provided
    launch_headless = headless if headless is not None else settings.browser_headless
    launch_width = browser_width if browser_width is not None else settings.browser_width
    launch_height = browser_height if browser_height is not None else settings.browser_height
    launch_devtools = devtools if devtools is not None else settings.browser_devtools

    cache = GoogleMapsCache()
    fresh_delta = timedelta(days=ttl_days)

    coordinates = None
    if "zip_code" in location_param:
        coordinates = get_coordinates_from_zip(location_param["zip_code"])
    elif "city" in location_param:
        coordinates = get_coordinates_from_city_state(location_param["city"])

    if not coordinates:
        print(f"Error: Could not find coordinates for {location_param}")
        return []

    latitude = coordinates["latitude"]
    longitude = coordinates["longitude"]

    base_url = "https://www.google.com/maps/search/"
    formatted_search_string = search_string.replace(" ", "+")
    url = f"{base_url}{formatted_search_string}/@{latitude},{longitude},15z/data=!3m2!1e3!4b1?entry=ttu"

    scraped_data: List[GoogleMapsData] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=launch_headless,
            devtools=launch_devtools,
            args=[f'--window-size={launch_width},{launch_height}']
        )
        page = browser.new_page(viewport={'width': launch_width, 'height': launch_height})

        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            print("Navigated to Google Maps URL.")

            scrollable_div_selector = 'div[role="feed"]'
            page.wait_for_selector(scrollable_div_selector)
            scrollable_div = page.locator(scrollable_div_selector)

            scraped_count = 0
            last_scroll_height = -1
            while scraped_count < max_results:
                listing_divs = scrollable_div.locator("> div").all()
                print(f"Found {len(listing_divs)} listing divs.")

                if not listing_divs:
                    print("No listing divs found. Exiting.")
                    break

                for listing_div in listing_divs:
                    html_content = listing_div.inner_html()
                    if html_content == '':
                        # If the div is empty
                        continue
                    if "All filters" in html_content:
                        # Filter header
                        continue
                    if "Prices come from Google" in html_content:
                        # Legal header
                        continue

                    business_data_dict = parse_business_listing_html(html_content, search_string, debug=debug)

                    if debug:
                        print("Debug: Pausing after parsing business listing HTML. Press F8 in Playwright Inspector to resume.")
                        page.pause() # Pause for debugging

                    place_id = business_data_dict.get("Place_ID")

                    if not place_id:
                        continue

                    # Check cache
                    cached_item = cache.get_by_place_id(place_id)
                    if cached_item and not force_refresh and (datetime.utcnow() - cached_item.updated_at < fresh_delta):
                        scraped_data.append(cached_item)
                        print(f"Used cached data for: {cached_item.Name}")
                        scraped_count += 1
                        continue

                    # If not in cache or stale, proceed with full scrape
                    # (parse_business_listing_html already did the initial parse)
                    gmb_url = business_data_dict.get("GMB_URL")
                    if gmb_url and (not business_data_dict.get("Website") or not business_data_dict.get("Full_Address")):
                        gmb_page = browser.new_page()
                        gmb_page.goto(gmb_url)
                        gmb_html = gmb_page.content()
                        gmb_data = parse_gmb_page(gmb_html)
                        business_data_dict.update(gmb_data)
                        gmb_page.close()

                    # Type conversions
                    for field in ['Reviews_count']:
                        if business_data_dict.get(field) and business_data_dict.get(field) != '':
                            try:
                                business_data_dict[field] = int(business_data_dict[field])
                            except (ValueError, TypeError):
                                business_data_dict[field] = None

                    for field in ['Average_rating', 'Latitude', 'Longitude']:
                        if business_data_dict.get(field) and business_data_dict.get(field) != '':
                            try:
                                business_data_dict[field] = float(business_data_dict[field])
                            except (ValueError, TypeError):
                                business_data_dict[field] = None

                    business_data = GoogleMapsData(**business_data_dict)
                    cache.add_or_update(business_data)
                    scraped_data.append(business_data)
                    scraped_count += 1
                    print(f"Scraped and cached: {business_data.Name} ({scraped_count}/{max_results})")

                    if scraped_count >= max_results:
                        break

                if scraped_count >= max_results:
                    break

                current_scroll_height = scrollable_div.evaluate("element => element.scrollHeight")
                if current_scroll_height == last_scroll_height:
                    print("Reached end of scrollable content.")
                    break

                scrollable_div.evaluate("element => element.scrollTop = element.scrollHeight")
                page.wait_for_timeout(delay_seconds * 1000)
                last_scroll_height = current_scroll_height

        except Exception as e:
            print(f"An error occurred during scraping: {e}")
        finally:
            cache.save()
            browser.close()

    return scraped_data
