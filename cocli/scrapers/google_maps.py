import csv
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from playwright.sync_api import sync_playwright, Page, Locator
from bs4 import BeautifulSoup
import uuid
from datetime import datetime
from cocli.core import load_scraper_settings # Import the settings loader

# Define the Lead Sniper CSV headers
LEAD_SNIPER_HEADERS = [
    "id",
    "Keyword",
    "Name",
    "Full_Address",
    "Street_Address",
    "City",
    "Zip",
    "Municipality",
    "State",
    "Country",
    "Timezone",
    "Phone_1",
    "Phone_Standard_format",
    "Phone_From_WEBSITE",
    "Email_From_WEBSITE",
    "Website",
    "Domain",
    "First_category",
    "Second_category",
    "Claimed_google_my_business",
    "Reviews_count",
    "Average_rating",
    "Business_Status",
    "Hours",
    "Saturday",
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Latitude",
    "Longitude",
    "Coordinates",
    "Plus_Code",
    "Place_ID",
    "Menu_Link",
    "GMB_URL",
    "CID",
    "Google_Knowledge_URL",
    "Kgmid",
    "Image_URL",
    "Favicon",
    "Review_URL",
    "Facebook_URL",
    "Linkedin_URL",
    "Instagram_URL",
    "Meta_Description",
    "Meta_Keywords",
    "Uuid",
    "Accessibility",
    "Service_options",
    "Amenities",
    "From_the_business",
    "Crowd",
    "Planning",
]

# Simple placeholder for zip code to coordinates mapping
# In a real application, this would involve a geocoding API or a more comprehensive lookup
ZIP_TO_COORDS = {
    "90210": {"latitude": 34.0736, "longitude": -118.4004}, # Beverly Hills, CA
    # Add more zip codes as needed for testing or expansion
}

def _get_coordinates_from_zip(zip_code: str) -> Optional[Dict[str, float]]:
    """
    Retrieves latitude and longitude for a given zip code.
    This is a placeholder and should be replaced with a proper geocoding service.
    """
    return ZIP_TO_COORDS.get(zip_code)

def scrape_google_maps(
    zip_code: str,
    search_string: str,
    output_dir: Path = Path("."), # Default to current directory, will be overridden by CLI
    max_results: int = 50, # This will be overridden by settings.google_maps_max_pages
):
    """
    Scrapes business information from Google Maps search results based on zip code and search string
    and outputs it to a CSV file in the Lead Sniper format.
    """
    settings = load_scraper_settings() # Load scraper settings
    delay_seconds = settings.google_maps_delay_seconds
    max_pages_to_scrape = settings.google_maps_max_pages

    coordinates = _get_coordinates_from_zip(zip_code)
    if not coordinates:
        print(f"Error: Could not find coordinates for zip code {zip_code}. Please provide a valid zip code.")
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


    print(f"Starting Google Maps scraping for search: '{search_string}' in zip code: {zip_code}")
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
                while scraped_count < max_results and pages_scraped < max_pages_to_scrape:
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
                    page.wait_for_timeout(delay_seconds * 1000)  # Wait for content to load after scroll
                    pages_scraped += 1

                    last_scroll_height = current_scroll_height

                    # Get all business listings after scrolling
                    # This selector targets the main clickable link for each business
                    business_links = page.locator("a.hfpxzc").all()

                    new_data_found_in_iteration = False
                    for link_locator in business_links:
                        gmb_url = link_locator.get_attribute("href")
                        if gmb_url and gmb_url not in processed_urls:
                            # Get the parent div that contains all the business info
                            # This selector might need adjustment based on actual Google Maps HTML
                            listing_container = link_locator.locator(
                                'xpath=ancestor::div[contains(@class, "Nv2PK")]'
                            ).first

                            if listing_container:
                                html_content = listing_container.inner_html()
                                business_data = _extract_business_data(
                                    html_content, search_string # Pass search_string as keyword
                                )

                                if business_data.get(
                                    "Name"
                                ):  # Only write if a name was extracted
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

        except Exception as e:
            print(f"An error occurred during scraping: {e}")
        finally:
            browser.close()


def _extract_business_data(
    item_html: str, keyword: Optional[str] = None
) -> Dict[str, Any]:
    """
    Extracts business data from a single Google Maps listing HTML snippet.
    """
    soup = BeautifulSoup(item_html, "html.parser")
    data: Dict[str, Any] = {header: "" for header in LEAD_SNIPER_HEADERS}
    data["Keyword"] = keyword if keyword else ""
    data["id"] = str(uuid.uuid4())  # Generate a unique ID
    data["Uuid"] = str(uuid.uuid4())  # Generate a unique UUID

    # Extract Name
    name_element = soup.select_one(".qBF1Pd.fontHeadlineSmall")
    if name_element:
        data["Name"] = name_element.text.strip()

    # Extract GMB URL
    gmb_url_element = soup.select_one("a.hfpxzc")
    if gmb_url_element and gmb_url_element.has_attr("href"):
        data["GMB_URL"] = gmb_url_element["href"]
        # Attempt to extract Latitude, Longitude, Coordinates, Place_ID from GMB_URL
        # The pattern is !3d<latitude>!4d<longitude>
        match = re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", data["GMB_URL"])
        if match:
            data["Latitude"] = match.group(1)
            data["Longitude"] = match.group(2)
            data["Coordinates"] = f"{match.group(1)},{match.group(2)}"

        place_id_match = re.search(r"!1s([^!]+)", data["GMB_URL"])
        if place_id_match:
            data["Place_ID"] = place_id_match.group(1)

    # Extract Rating and Reviews Count
    rating_element = soup.select_one(".MW4etd")
    if rating_element:
        data["Average_rating"] = rating_element.text.strip()

    reviews_count_element = soup.select_one(".UY7F9")
    if reviews_count_element:
        data["Reviews_count"] = reviews_count_element.text.strip("()").replace(",", "")

    # Refined extraction for Address, Phone, Categories, Business Status, Hours
    # Target the specific div.W4Efsd blocks
    info_blocks = soup.select(".W4Efsd")

    # Find the block that contains the category and address
    category_address_block = None
    for block in info_blocks:
        # Check if the block contains a span with text that looks like a category
        if block.find(
            "span", string=re.compile(r"(photography|studio)", re.IGNORECASE)
        ):
            category_address_block = block
            break

    if category_address_block:
        # Category
        category_element = category_address_block.select_one("span span")
        if category_element:
            data["First_category"] = category_element.text.strip()

        # Address: Find the span that contains the address text directly
        # Look for a span whose text starts with a digit (common for street numbers)
        address_text_element = category_address_block.find(string=re.compile(r"^\d+.*"))
        if address_text_element:
            data["Full_Address"] = address_text_element.strip()
            # Basic address parsing
            address_components = [p.strip() for p in data["Full_Address"].split(",")]
            if len(address_components) >= 1:
                data["Street_Address"] = address_components[0]
            if len(address_components) >= 2:
                data["City"] = address_components[1]
            if len(address_components) >= 3:
                state_zip_match = re.search(
                    r"([A-Z]{2})\s*(\d{5})", address_components[2]
                )
                if state_zip_match:
                    data["State"] = state_zip_match.group(1)
                    data["Zip"] = state_zip_match.group(2)
                else:
                    data["State"] = address_components[2]
            if len(address_components) >= 4:
                data["Country"] = address_components[3]

    # Find the block that contains business status, hours, and phone
    status_hours_phone_block = None
    for block in info_blocks:
        if block.find("span", string=re.compile(r"(Open|Closes)", re.IGNORECASE)):
            status_hours_phone_block = block
            break

    if status_hours_phone_block:
        # Business Status (Open/Closed)
        status_element = status_hours_phone_block.select_one(
            "span[style*='font-weight: 400; color: rgba(25,134,57,1.00);']"
        )
        if status_element:
            data["Business_Status"] = status_element.text.strip()

        # Hours: Find the span that contains "Open", then get its next sibling
        open_span = status_hours_phone_block.find("span", string="Open")
        if open_span and open_span.find_next_sibling("span"):
            hours_text_element = open_span.find_next_sibling("span")
            if hours_text_element:
                full_hours_text = hours_text_element.text.strip()
                # Replace Narrow No-Break Space with regular space
                full_hours_text = full_hours_text.replace("\u202f", " ")
                # Extract "Closes 6 PM" part
                match = re.search(r"Closes\s*\d+\s*PM", full_hours_text)
                if match:
                    data["Hours"] = match.group(0)
                else:
                    # Fallback if the specific "Closes X PM" pattern is not found
                    data["Hours"] = full_hours_text

        # Phone number
        phone_element = status_hours_phone_block.select_one("span.UsdlK")
        if phone_element:
            data["Phone_1"] = phone_element.text.strip()
            data["Phone_Standard_format"] = phone_element.text.strip()

    # Extract Website URL
    # Try the data-value attribute first
    website_element = soup.select_one("a[data-value='Website']")
    if website_element and website_element.has_attr("href"):
        data["Website"] = website_element["href"]

    if not data["Website"]: # If not found by data-value, try other methods
        # Fallback 1: look for any link with "Website" in text or aria-label
        for link in soup.find_all("a", href=True):
            href = link["href"]
            link_text = link.text.strip().lower()
            aria_label = link.get("aria-label", "").lower()

            if "website" in link_text or "website" in aria_label:
                if (
                    href.startswith("http")
                    and "google.com/maps" not in href
                    and "maps.google.com" not in href
                ):
                    data["Website"] = href
                    break

    if not data["Website"]: # Fallback 2: look for any general http/https link not related to maps, but contains a domain pattern
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if (
                href.startswith("http")
                and "google.com/maps" not in href
                and "maps.google.com" not in href
                and re.search(r'\.(com|org|net|io|co|us|gov|edu)', href) # Look for common TLDs
            ):
                data["Website"] = href
                break

    if data["Website"]:
        domain_match = re.search(r"https?://(?:www\.)?([^/]+)", data["Website"])
        if domain_match:
            data["Domain"] = domain_match.group(1)

    # Social Media URLs (Facebook, LinkedIn, Instagram) - not directly in item.html, will be empty for now
    # Meta Description/Keywords - not directly in item.html, will be empty for now

    return data
