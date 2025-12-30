
from typing import Optional, Dict, Any
from playwright.sync_api import sync_playwright
from .google_maps_parser import parse_business_listing_html
import logging

logger = logging.getLogger(__name__)

def find_business_on_google_maps(
    company_name: str,
    location_param: Dict[str, str],
    debug: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Finds a single business on Google Maps and returns its data.
    """
    
    base_url = "https://www.google.com/maps/search/"
    
    # Construct search query from company name and available location info
    location_str = location_param.get("address") or location_param.get("city") or ""
    search_query = f"{company_name} {location_str}".strip()
    formatted_search_string = search_query.replace(" ", "+")
    
    url = f"{base_url}{formatted_search_string}/"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded")
            # Wait for either the list (feed) or a direct business view (canvas/main layout)
            try:
                page.wait_for_selector('div[role="feed"], h1.DUwDvf', timeout=10000)
            except Exception:
                # If neither shows up quickly, it might still be loading or a different layout
                page.wait_for_timeout(2000)

            scrollable_div_selector = 'div[role="feed"]'
            direct_name_selector = 'h1.DUwDvf' # Selector for the business name in direct view
            
            if page.locator(scrollable_div_selector).count() > 0:
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
            
            elif page.locator(direct_name_selector).count() > 0:
                # Direct view - we need to extract Place ID from the URL or metadata
                # For now, let's try to extract Place ID from the current URL
                current_url = page.url
                # Example URL: .../place/CompanyName/@lat,long,zoom/data=!3m1!4b1!4m6!3m5!1sPLACE_ID...
                # Place ID often follows 1s in the data param
                import re
                place_id_match = re.search(r'!1s(ChIJ[a-zA-Z0-9_-]+)', current_url)
                if place_id_match:
                    place_id = place_id_match.group(1)
                    # Return a minimal dict that matches what the caller expects
                    return {
                        "Name": page.locator(direct_name_selector).inner_text(),
                        "Place_ID": place_id
                    }
                
            return None

        except Exception as e:
            import sys
            location_str = location_param.get("address") or location_param.get("city") or "Unknown Location"
            msg = f"An error occurred during scraping {company_name} in {location_str}: {e}"
            logger.error(msg)
            print(f"\n[Scraper Error] {msg}", file=sys.stderr)
            return None
        finally:
            browser.close()
