import re
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

def extract_phone_number(soup: BeautifulSoup, inner_text: str, debug: bool = False) -> str:
    """
    Extracts the phone number from innerText or falls back to HTML selectors.
    """
    phone_number = ""
    phone_match = re.search(r"(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})", inner_text)
    if phone_match:
        phone_number = phone_match.group(1).strip()
        if debug:
            logger.debug(f"Extracted Phone_1 (innerText): {phone_number}")
    else:
        # Fallback to HTML selector
        phone_element = soup.find("button", attrs={"data-tooltip": "Copy phone number"})
        if phone_element:
            phone_number = str(phone_element.get("aria-label", "")).replace("Phone: ", "").strip()
            if debug:
                logger.debug(f"Extracted Phone_1 (HTML fallback): {phone_number}")
        else:
            if debug:
                logger.debug("Phone number element not found from innerText or HTML fallback.")
    return phone_number