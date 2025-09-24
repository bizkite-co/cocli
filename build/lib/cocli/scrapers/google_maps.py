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


def scrape_google_maps(
    location_param: Dict[str, str], # Accepts either {"zip_code": "..."} or {"city": "..."}
    search_string: str,
    output_dir: Path = get_scraped_data_dir(),  # Default to scraped data directory
    max_results: int = 200,  # Increased max_results to allow more scraping
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
    print(
        f"Starting Google Maps scraping for search: '{search_string}' in location: {location_display}"
    )
    print(f"Generated URL: {url}")
    print(f"Using delay: {delay_seconds} seconds, Max pages: {max_pages_to_scrape}")

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    output_filename = f"lead-sniper-{re.sub(r'[^a-zA-Z0-9_]', '-', search_string.lower())}-{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    output_filepath = output_dir / output_filename

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded")
            print("Navigated to Google Maps URL.")

            with open(output_filepath, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=LEAD_SNIPER_HEADERS)
                writer.writeheader()

                # Find the scrollable element (usually the results pane)
                # The main scrollable results pane often has role="feed" or a specific data-attribute
                scrollable_div_selector = 'div[role="feed"]'
                page.wait_for_selector(scrollable_div_selector)
                scrollable_div = page.locator(scrollable_div_selector)

                scraped_count = 0
                pages_scraped = 0
                processed_urls = (
                    set()
                )  # To keep track of unique businesses by their GMB URL

                # Use a loop to scroll and extract until max_results or no new content
                last_scroll_height = -1
                while (
                    scraped_count < max_results and pages_scraped < max_pages_to_scrape
                ):
                    # Scroll to the bottom of the scrollable div
                    current_scroll_height = scrollable_div.evaluate(
                        "element => element.scrollHeight"
                    )
                    if current_scroll_height == last_scroll_height:
                        print(
                            "Reached end of scrollable content or no new results loaded."
                        )
                        break  # No new content loaded, stop scrolling

                    scrollable_div.evaluate(
                        "element => element.scrollTop = element.scrollHeight"
                    )
                    page.wait_for_timeout(
                        delay_seconds * 1000
                    )  # Wait for content to load after scroll
                    pages_scraped += 1

                    last_scroll_height = current_scroll_height

                    # Get all top-level div elements within the scrollable feed
                    # These are the potential business listings
                    listing_divs = scrollable_div.locator("div > div").all() # Adjust selector if needed

                    new_data_found_in_iteration = False
                    for listing_div in listing_divs:
                        # Check if the div contains content indicative of a business listing
                        # This is a heuristic and might need refinement
                        inner_text = listing_div.inner_text()
                        if any(keyword in inner_text for keyword in [search_string, "reviews", "stars", "address", "phone", "website"]):
                            html_content = listing_div.inner_html()
                            business_data = parse_business_listing_html( # Use the new parser function
                                html_content,
                                search_string,  # Pass search_string as keyword
                                debug=debug # Pass the debug flag
                            )

                            # Extract GMB URL from the business_data, as it's now extracted within _extract_business_data
                            gmb_url = business_data.get("GMB_URL")

                            if gmb_url and gmb_url not in processed_urls and business_data.get("Name"):  # Only write if a name was extracted and URL is unique
                                writer.writerow(business_data)
                                processed_urls.add(gmb_url)
                                scraped_count += 1
                                new_data_found_in_iteration = True
                                print(
                                    f"Scraped: {business_data.get('Name')} ({scraped_count}/{max_results})"
                                )

                            if scraped_count >= max_results:
                                break  # Break from inner loop if max results reached

                    if scraped_count >= max_results:
                        break  # Break from outer loop if max results reached

                    if not new_data_found_in_iteration and scraped_count > 0:
                        print(
                            "No new unique data found in this scroll iteration. Stopping."
                        )
                        break

                print(f"CSV file created at: {output_filepath}")

            print("Scraping complete (initial setup).")
            return output_filepath

        except Exception as e:
            print(f"An error occurred during scraping: {e}")
            return None # Return None on error
        finally:
            browser.close()
