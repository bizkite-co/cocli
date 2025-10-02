import csv
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from playwright.sync_api import sync_playwright, Page, Locator
from bs4 import BeautifulSoup
import uuid
from datetime import datetime
from ..core.config import load_scraper_settings  # Import the settings loader
from ..core.config import get_scraped_data_dir # Import the new function
from ..core.geocoding import get_coordinates_from_zip
from ..core.geocoding import get_coordinates_from_city_state # Import the geocoding function
from .google_maps_parser import parse_business_listing_html, LEAD_SNIPER_HEADERS # Import the new parser and headers
from .google_maps_gmb_parser import parse_gmb_page


def scrape_google_maps(
    location_param: Dict[str, str], # Accepts either {"zip_code": "..."} or {"city": "..."}
    search_string: str,
    output_dir: Path = get_scraped_data_dir(),  # Default to scraped data directory
    max_results: int = 30,  # Increased max_results to allow more scraping
    debug: bool = False, # Added debug parameter
) -> Path:
    """
    Scrapes business information from Google Maps search results based on location (zip code or city/state) and search string
    and outputs it to a CSV file in the Lead Sniper format.
    """
    if debug: print(f"Debug: scrape_google_maps called with debug={debug}")
    settings = load_scraper_settings()  # Load scraper settings
    delay_seconds = settings.google_maps_delay_seconds # Use configured delay
    max_pages_to_scrape = settings.google_maps_max_pages # Use configured max pages

    # Override settings for more aggressive scraping during debug/testing
    if debug:
        delay_seconds = 5 # Reduced delay for faster debugging
        max_pages_to_scrape = 5 # Increased max pages for more results

    coordinates = None
    if "zip_code" in location_param:
        coordinates = get_coordinates_from_zip(location_param["zip_code"])
        if not coordinates:
            print(f"Error: Could not find coordinates for zip code {location_param['zip_code']}. Please provide a valid zip code.")
            return
    elif "city" in location_param:
        coordinates = get_coordinates_from_city_state(location_param["city"])
        if not coordinates:
            print(f"Error: Could not find coordinates for city/state {location_param['city']}. Please provide a valid city/state.")
            return
    else:
        print("Error: Invalid location parameter provided. Must be either 'zip_code' or 'city'.")
        return

    latitude = coordinates["latitude"]
    longitude = coordinates["longitude"]

    # Construct the Google Maps URL
    # Example URL: https://www.google.com/maps/search/photography+studio/@33.9351822,-117.8542484,99708m/data=!3m2!1e3!4b1?entry=ttu
    # The '99708m' is a zoom level, 'data=!3m2!1e3!4b1?entry=ttu' are additional parameters.
    # For simplicity, we'll use a fixed zoom and data parameters for now.
    # A more robust solution might dynamically determine zoom or allow it as a parameter.
    base_url = "https://www.google.com/maps/search/"
    formatted_search_string = search_string.replace(" ", "+")
    url = f"{base_url}{formatted_search_string}/@{latitude},{longitude},15z/data=!3m2!1e3!4b1?entry=ttu"

    location_display = location_param.get("zip_code") or location_param.get("city")
    search_slug = re.sub(r'[^a-zA-Z0-9_]', '-', search_string.lower())
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    output_filename = f"{timestamp}-{location_display.replace(', ', '-')}-{search_slug}.csv"
    output_filepath = output_dir / output_filename

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(5000) # Wait for dynamic content to load
            print("Navigated to Google Maps URL.")

            with open(output_filepath, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=LEAD_SNIPER_HEADERS)
                writer.writeheader()

                # Find the scrollable element (usually the results pane)
                # The main scrollable results pane often has role="feed" or a specific data-attribute
                scrollable_div_selector = 'div[role="feed"]'
                page.wait_for_selector(scrollable_div_selector)
                scrollable_div = page.locator(scrollable_div_selector)

                while scraped_count < max_results:
                    listing_divs = scrollable_div.locator("> div").all()
                    print(f"Found {len(listing_divs)} listing divs.")

                    if not listing_divs:
                        print("No listing divs found. Exiting.")
                        return

                    for i, listing_div in enumerate(listing_divs):
                        inner_text = listing_div.inner_text()
                        print(f"-- Listing {i} --\n{inner_text[:200]}\n-----------------")
                        if not inner_text.strip():
                            continue

                        html_content = listing_div.inner_html()
                        business_data = parse_business_listing_html(
                            html_content,
                            search_string,
                            debug=debug
                        )

                        # Filter out stores
                        if "store" in business_data.get("Name", "").lower() or \
                           "store" in business_data.get("First_category", "").lower():
                            print(f"Skipping store: {business_data.get('Name')}")
                            continue

                        gmb_url = business_data.get("GMB_URL")

                        if gmb_url:
                            gmb_page = browser.new_page()
                            gmb_page.goto(gmb_url)
                            gmb_html = gmb_page.content()
                            gmb_data = parse_gmb_page(gmb_html)
                            business_data.update(gmb_data)
                            gmb_page.close()

                        if gmb_url and gmb_url not in processed_urls and business_data.get("Name"):
                            writer.writerow(business_data)
                            processed_urls.add(gmb_url)
                            scraped_count += 1
                            print(f"Scraped: {business_data.get('Name')} ({scraped_count}/{max_results})")

                        if scraped_count >= max_results:
                            break

                    if scraped_count >= max_results:
                        break

                    current_scroll_height = scrollable_div.evaluate("element => element.scrollHeight")
                    if current_scroll_height == last_scroll_height:
                        print("Reached end of scrollable content or no new results loaded.")
                        break

                    scrollable_div.evaluate("element => element.scrollTop = element.scrollHeight")
                    page.wait_for_timeout(delay_seconds * 1000)
                    pages_scraped += 1
                    last_scroll_height = current_scroll_height

                print(f"CSV file created at: {output_filepath}")

            print("Scraping complete (initial setup).")
            return output_filepath

        except Exception as e:
            print(f"An error occurred during scraping: {e}")
            return None # Return None on error
        finally:
            browser.close()
