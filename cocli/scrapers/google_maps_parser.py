import re
import uuid
from typing import Dict, Any, Optional
from bs4 import BeautifulSoup

from .google_maps_parsers.extract_name import extract_name
from .google_maps_parsers.extract_rating_reviews import extract_rating_reviews
from .google_maps_parsers.extract_address import extract_address
from .google_maps_parsers.extract_phone_number import extract_phone_number
from .google_maps_parsers.extract_website import extract_website
from .google_maps_parsers.extract_categories import extract_categories
from .google_maps_parsers.extract_business_status_hours import extract_business_status_hours
from .google_maps_parsers.extract_gmb_url_coordinates_place_id import extract_gmb_url_coordinates_place_id

GOOGLE_MAPS_HEADERS = [
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
    "Thumbnail_URL",
    "Reviews",
    "Quotes",
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

QUOTES_RE = re.compile(r'"(.*?)"')

def parse_business_listing_html(
    item_html: str, keyword: Optional[str] = None, debug: bool = False
) -> Dict[str, Any]:
    """
    Extracts business data from a single Google Maps listing HTML snippet, prioritizing innerText parsing.
    """
    soup = BeautifulSoup(item_html, "html.parser")
    data: Dict[str, Any] = {header: "" for header in GOOGLE_MAPS_HEADERS}
    data["Keyword"] = keyword if keyword else ""
    data["id"] = str(uuid.uuid4())  # Generate a unique ID
    data["Uuid"] = str(uuid.uuid4())  # Generate a unique UUID NOTE: We don't need two of these.

    if debug: print(f"Debug: Processing HTML: {item_html[:500]}...") # Print first 500 chars of HTML
    inner_text = soup.get_text(separator="\n", strip=True)
    if debug: print(f"Debug: Processing innerText: {inner_text[:500]}...") # Print first 500 chars of innerText

    # Extract data using modular functions
    data["Name"] = extract_name(soup, inner_text, debug)

    rating_reviews = extract_rating_reviews(soup, inner_text, debug)
    data.update(rating_reviews)

    address_data = extract_address(soup, inner_text, debug)
    data.update(address_data)

    data["Phone_1"] = extract_phone_number(soup, inner_text, debug)
    data["Phone_Standard_format"] = data["Phone_1"] # Standard format is same as Phone_1 for now

    website_data = extract_website(soup, inner_text, debug)
    data.update(website_data)

    category_data = extract_categories(soup, inner_text, debug)
    data.update(category_data)

    gmb_data = extract_gmb_url_coordinates_place_id(soup, debug)
    data.update(gmb_data)

    business_status_hours = extract_business_status_hours(soup, inner_text, debug)
    data.update(business_status_hours)

    # Extract quotes
    quotes = QUOTES_RE.findall(inner_text)
    data["Quotes"] = "\n".join(quotes)

    if debug: print(f"Debug: Final extracted data: {data}")
    return data