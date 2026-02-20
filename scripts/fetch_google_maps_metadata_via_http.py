import sys
import os
import requests
import re
from typing import Optional
from bs4 import BeautifulSoup
import argparse

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__name__), "..")))
from cocli.models.campaigns.indexes.google_maps_raw import GoogleMapsRawResult

def fetch_google_maps_metadata_via_http(place_id: str) -> Optional[GoogleMapsRawResult]:
    """
    Retrieves basic business metadata (Name, Address) for a Place ID using 
    a light HTTP GET request.
    """
    # This URL often returns a page with the business name in the title
    url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
    }
    
    try:
        session = requests.Session()
        response = session.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # Google often redirects to a more specific URL that includes the name/slug
        final_url = response.url
        
        # If the URL changed, we might be able to extract the name from it
        # Example: .../maps/place/Business+Name/@...
        name_from_url = ""
        place_match = re.search(r"/maps/place/([^/]+)/", final_url)
        if place_match:
            name_from_url = place_match.group(1).replace("+", " ")

        soup = BeautifulSoup(response.text, "html.parser")
        
        # Priority 1: Title (usually "[Name] - Google Maps")
        title = soup.find("title")
        name = ""
        if title:
            name = title.get_text().replace(" - Google Maps", "").strip()
        
        # If title is still "Google Maps", use the URL name
        if (not name or name == "Google Maps") and name_from_url:
            name = name_from_url

        # Priority 2: og:title
        if not name or name == "Google Maps":
            og_title = soup.find("meta", property="og:title")
            if og_title:
                name = og_title.get("content", "").split(" · ")[0]

        # Address Extraction
        address = ""
        og_description = soup.find("meta", property="og:description")
        if og_description:
            address = og_description.get("content", "").strip()
            # If description is the generic "Find local businesses...", it's useless
            if "Find local businesses" in address:
                address = ""

        # Last Resort: Search the page content for address-like strings if we have a name
        # (This is harder without Playwright, but we can try to find JSON-LD)
        if not address:
            script_tags = soup.find_all("script")
            for script in script_tags:
                if script.string and '"' + name + '"' in script.string:
                    # Look for address-like pattern near the name in the JS blob
                    # This is very brittle but sometimes works
                    match = re.search(r"\"([^\"]+\d{5}[^\"]*)\"", script.string)
                    if match:
                        address = match.group(1)
                        break

        if name and name != "Google Maps":
            return GoogleMapsRawResult(
                Place_ID=place_id,
                Name=name,
                Full_Address=address or "Address Pending",
                processed_by="http-recovery-agent"
            )
            
    except Exception as e:
        print(f"HTTP request failed for {place_id}: {e}")
        
    return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("place_id")
    args = parser.parse_args()
    res = fetch_google_maps_metadata_via_http(args.place_id)
    if res:
        print(f"Name: {res.Name}")
        print(f"Address: {res.Full_Address}")
    else:
        print("Failed.")