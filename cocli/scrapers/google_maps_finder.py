
from typing import Optional, Dict, Any
from playwright.sync_api import sync_playwright, Page
from .google_maps_parser import parse_business_listing_html
from ..core.geocoding import get_coordinates_from_city_state, get_coordinates_from_zip, get_coordinates_from_address
import re

def find_business_on_google_maps(
    company_name: str,
    location_param: Dict[str, str],
    debug: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Finds a single business on Google Maps and returns its data.
    """
    
    coordinates = None
    if "address" in location_param:
        coordinates = get_coordinates_from_address(location_param["address"])
    elif "zip_code" in location_param:
        coordinates = get_coordinates_from_zip(location_param["zip_code"])
    elif "city" in location_param:
        coordinates = get_coordinates_from_city_state(location_param["city"])
        
    if not coordinates:
        print(f"Could not find coordinates for {location_param}")
        return None

    latitude = coordinates["latitude"]
    longitude = coordinates["longitude"]

    base_url = "https://www.google.com/maps/search/"
    formatted_search_string = company_name.replace(" ", "+")
    url = f"{base_url}{formatted_search_string}/@{latitude},{longitude},15z/data=!3m2!1e3!4b1?entry=ttu"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(5000) # Wait for dynamic content to load

            scrollable_div_selector = 'div[role="feed"]'
            page.wait_for_selector(scrollable_div_selector)
            scrollable_div = page.locator(scrollable_div_selector)

            listing_divs = scrollable_div.locator("> div").all()

            if not listing_divs:
                return None

            # Find the best match
            best_match_score = 0
            best_match_data = None

            for listing_div in listing_divs:
                inner_text = listing_div.inner_text()
                if not inner_text.strip():
                    continue

                html_content = listing_div.inner_html()
                business_data = parse_business_listing_html(
                    html_content,
                    company_name,
                    debug=debug
                )

                # Use fuzzy matching to find the best match
                from fuzzywuzzy import fuzz # type: ignore
                score = fuzz.ratio(company_name.lower(), business_data.get("Name", "").lower())

                if score > best_match_score:
                    best_match_score = score
                    best_match_data = business_data

            return best_match_data

        except Exception as e:
            print(f"An error occurred during scraping: {e}")
            return None
        finally:
            browser.close()
