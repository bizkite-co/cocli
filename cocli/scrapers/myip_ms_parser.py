from typing import Dict, Any
import re
import logging

logger = logging.getLogger(__name__)

# Define headers for the Shopify data, aligning with Lead Sniper where possible
SHOPIFY_HEADERS = [
    "id",
    "Keyword", # Can be "shopify-myip-ms" or similar
    "Name", # Will be derived from Website domain
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
    "Accessibility",
    "Service_options",
    "Amenities",
    "From_the_business",
    "Crowd",
    "Planning",
    "IP_Address", # New field for myip.ms data
    "Popularity_Visitors_Per_Day", # New field for myip.ms data
    "Scrape_Date", # New field for myip.ms data
]

from ..core.utils import generate_company_hash

def extract_domain_from_url(url: str) -> str:
    """Extracts the domain from a given URL."""
    if not url:
        return ""
    match = re.search(r"https?://(?:www\.)?([a-zA-Z0-9.-]+)", url)
    return match.group(1) if match else ""

def parse_myip_ms_listing(row_data: Dict[str, str], debug: bool = False) -> Dict[str, Any]:
    """
    Parses a single row of data from myip.ms (or converted XLSX) into a structured format
    compatible with the Company model.
    """
    data: Dict[str, Any] = {header: "" for header in SHOPIFY_HEADERS}
    data["Keyword"] = "shopify-myip-ms" # Default keyword for this source

    if debug: logger.debug(f"Raw row data for parser: {row_data}")

    # Map fields from myip.ms CSV to SHOPIFY_HEADERS
    data["Website"] = row_data.get("Website", "")
    data["IP_Address"] = row_data.get("IP_Address", "")
    data["Popularity_Visitors_Per_Day"] = row_data.get("Popularity_Visitors_Per_Day", "")
    data["Country"] = row_data.get("Country", "")
    data["Scrape_Date"] = row_data.get("Scrape_Date", "")

    # Derive Name and Domain from Website
    if data["Website"]:
        data["Domain"] = extract_domain_from_url(data["Website"])
        # Attempt to derive a name from the domain, e.g., "example.com" -> "Example Com"
        if data["Domain"]:
            name_parts = data["Domain"].replace(".com", "").replace(".net", "").replace(".org", "").split('.')
            data["Name"] = " ".join([part.capitalize() for part in name_parts if part]).strip()
            if not data["Name"]:
                data["Name"] = data["Domain"]

    data["id"] = generate_company_hash(data)

    if debug: logger.debug(f"Parsed data: {data}")
    return data
