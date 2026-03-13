import re
from bs4 import BeautifulSoup
from typing import Dict
import logging

logger = logging.getLogger(__name__)

def extract_address(soup: BeautifulSoup, inner_text: str, debug: bool = False) -> Dict[str, str]:
    """
    Extracts address components from a soup object, preferring specific HTML structure,
    and falling back to innerText parsing.
    """
    full_address = ""
    street_address = ""
    city = ""
    zip_code = ""
    state = ""
    country = ""

    # Primary Method: Find the specific div and parse its contents
    # The address is typically in a div that contains other info separated by '·'
    address_divs = soup.find_all('div', class_='W4Efsd')
    address_text = ""
    for div in address_divs:
        text = div.get_text(separator='|', strip=True)
        if '·' in text and re.search(r'\d', text): # A simple check for a digit, common in addresses
            parts = [p.strip() for p in text.split('|') if p.strip()]
            try:
                # Find the index of the last part containing '·'
                # If no part has '·', last_dot_index should be -1
                last_dot_index_of_part = -1
                for i, part in enumerate(parts):
                    if '·' in part:
                        last_dot_index_of_part = i
                
                if last_dot_index_of_part != -1 and (last_dot_index_of_part + 1 < len(parts)):
                    # Address is after the last '·' separated part
                    potential_address = parts[last_dot_index_of_part + 1]
                    logger.debug(f"Potential address after last '·' part: {potential_address}")
                elif last_dot_index_of_part != -1 and (last_dot_index_of_part < len(parts)):
                    # Address is the last part containing '·'
                    potential_address = parts[last_dot_index_of_part]
                    logger.debug(f"Potential address is the last '·' part: {potential_address}")
                else:
                    # No '·' or address is the first part
                    potential_address = parts[0] if parts else ""
                    logger.debug(f"Potential address is first part or empty, no '·' found: {potential_address}")

                # Basic validation: does it look like an address?
                if re.search(r'\d.*[a-zA-Z]', potential_address):
                    address_text = potential_address
                    logger.debug(f"Found potential address text: {address_text}")
                    break
            except Exception as e:
                logger.debug(f"Error during primary address extraction attempt: {e}")
                continue # Continue to next div or fallback

    if address_text:
        full_address = address_text
        logger.debug(f"Extracted Full_Address (Primary Method): {full_address}")
        # Simple parsing of the extracted address string
        address_components = [p.strip() for p in full_address.split(',')]
        if len(address_components) >= 1:
            street_address = address_components[0]
        if len(address_components) >= 2:
            city = address_components[1]
        if len(address_components) >= 3:
            state_zip_match = re.search(r'([A-Z]{2})\s*(\d{5})', address_components[2])
            if state_zip_match:
                state = state_zip_match.group(1)
                zip_code = state_zip_match.group(2)
            else:
                state = address_components[2]
        if len(address_components) >= 4:
            country = address_components[3]
    else:
        # Fallback to regex on inner_text if the primary method fails
        logger.debug("Primary address extraction failed, falling back to innerText regex.")
        # This regex is brittle and should be considered a last resort.
        # It looks for a line that likely contains an address (number and letters).
        # It avoids lines that look like phone numbers.
        address_match = re.search(r'^([^·(]*\d[^·(]*[a-zA-Z][^·(]*)$', inner_text, re.MULTILINE)
        if address_match:
            full_address = address_match.group(1).strip()
            logger.debug(f"Extracted Full_Address (innerText fallback): {full_address}")
            # Parsing logic is repeated here, could be refactored
            address_components = [p.strip() for p in full_address.split(',')]
            if len(address_components) >= 1:
                street_address = address_components[0]
            if len(address_components) >= 2:
                city = address_components[1]
            if len(address_components) >= 3:
                state_zip_match = re.search(r'([A-Z]{2})\s*(\d{5})', address_components[2])
                if state_zip_match:
                    state = state_zip_match.group(1)
                    zip_code = state_zip_match.group(2)
                else:
                    state = address_components[2]
            if len(address_components) >= 4:
                country = address_components[3]
        else:
            logger.debug("Address not found in innerText fallback either.")


    return {
        "Full_Address": full_address,
        "Street_Address": street_address,
        "City": city,
        "Zip": zip_code,
        "State": state,
        "Country": country,
    }
