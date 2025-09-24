import re
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional

def extract_address(soup: BeautifulSoup, inner_text: str, debug: bool = False) -> Dict[str, str]:
    """
    Extracts address components from innerText or falls back to HTML selectors.
    """
    full_address = ""
    street_address = ""
    city = ""
    zip_code = ""
    state = ""
    country = ""

    # Look for a pattern like "NUMBER StreetName, City, State ZIP"
    # This regex is more specific to avoid matching ratings
    address_match = re.search(r"(\d+[\w\s\.]+(?:Ave|Street|Road|Rd|Blvd|Place|Pl|Hwy|Ct|Circle|Dr|Lane|Ln|Parkway|Pkwy|Square|Sq|Terrace|Trl|Way|Wy)\.?,?\s*[\w\s]+,?\s*[A-Z]{2}\s*\d{5})", inner_text)
    if address_match:
        full_address = address_match.group(1).strip()
        if debug: print(f"Debug: Extracted Full_Address (innerText): {full_address}")
        address_components = [p.strip() for p in full_address.split(",")]
        if len(address_components) >= 1:
            street_address = address_components[0]
        if len(address_components) >= 2:
            city = address_components[1]
        if len(address_components) >= 3:
            state_zip_match = re.search(r"([A-Z]{2})\s*(\d{5})", address_components[2])
            if state_zip_match:
                state = state_zip_match.group(1)
                zip_code = state_zip_match.group(2)
            else:
                state = address_components[2]
        if len(address_components) >= 4:
            country = address_components[3]
        if debug: print(f"Debug: Parsed Address (innerText): Street={street_address}, City={city}, State={state}, Zip={zip_code}, Country={country}")
    else:
        # Fallback to HTML selectors
        address_element = soup.find("button", attrs={"data-tooltip": "Copy address"})
        if address_element:
            full_address = address_element.get("aria-label", "").replace("Address: ", "").strip()
            if debug: print(f"Debug: Extracted Full_Address (HTML fallback): {full_address}")
            address_components = [p.strip() for p in full_address.split(",")]
            if len(address_components) >= 1:
                street_address = address_components[0]
            if len(address_components) >= 2:
                city = address_components[1]
            if len(address_components) >= 3:
                state_zip_match = re.search(r"([A-Z]{2})\s*(\d{5})", address_components[2])
                if state_zip_match:
                    state = state_zip_match.group(1)
                    zip_code = state_zip_match.group(2)
                else:
                    state = address_components[2]
            if len(address_components) >= 4:
                country = address_components[3]
            if debug: print(f"Debug: Parsed Address (HTML fallback): Street={street_address}, City={city}, State={state}, Zip={zip_code}, Country={country}")
        else:
            if debug: print("Debug: Address element not found (HTML fallback).")

    return {
        "Full_Address": full_address,
        "Street_Address": street_address,
        "City": city,
        "Zip": zip_code,
        "State": state,
        "Country": country,
    }