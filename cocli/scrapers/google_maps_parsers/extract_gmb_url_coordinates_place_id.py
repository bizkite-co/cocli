import re
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

def extract_gmb_url_coordinates_place_id(soup: BeautifulSoup, debug: bool = False) -> Dict[str, str]:
    """
    Extracts GMB URL, Latitude, Longitude, Coordinates, and Place_ID from HTML.
    """
    gmb_url = ""
    latitude = ""
    longitude = ""
    coordinates = ""
    place_id = ""

    # This remains HTML-based as it's an attribute, not easily in innerText
    gmb_url_element = soup.find("a", class_="hfpxzc")
    if gmb_url_element and gmb_url_element.has_attr("href"):
        gmb_url = gmb_url_element["href"]
        if debug: logger.debug(f"Extracted GMB_URL (HTML): {gmb_url}")

        # Attempt to extract Latitude, Longitude, Coordinates, Place_ID from GMB_URL
        match = re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", gmb_url)
        if match:
            latitude = match.group(1)
            longitude = match.group(2)
            coordinates = f"{match.group(1)},{match.group(2)}"
            if debug: logger.debug(f"Extracted Coordinates (HTML): {coordinates}")
        else:
            if debug: logger.debug("Coordinates not found in GMB_URL.")

        place_id_match = re.search(r'(ChI[a-zA-Z0-9_-]+)', gmb_url)
        if place_id_match:
            place_id = place_id_match.group(1)
            if debug: logger.debug(f"Extracted Place_ID (HTML): {place_id}")
        else:
            if debug: logger.debug("Place_ID not found in GMB_URL.")
    else:
        if debug: logger.debug("GMB URL element not found (HTML).")

    return {
        "GMB_URL": gmb_url,
        "Latitude": latitude,
        "Longitude": longitude,
        "Coordinates": coordinates,
        "Place_ID": place_id,
    }