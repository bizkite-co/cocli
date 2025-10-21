import re
from bs4 import BeautifulSoup
from typing import Dict
import logging

logger = logging.getLogger(__name__)

STATUS_HOURS_RE = re.compile(r"(Open|Closed|Closes|Opens)\s*(.*?)(?:\n|$)", re.IGNORECASE)
HOURS_RE = re.compile(r"⋅\s*(.*)")

def extract_business_status_hours(soup: BeautifulSoup, inner_text: str, debug: bool = False) -> Dict[str, str]:
    """
    Extracts business status and hours from innerText or falls back to HTML selectors.
    """
    business_status = ""
    hours = ""

    # Look for "Open", "Closed", "Closes X PM", "Opens X AM/PM"
    status_hours_match = STATUS_HOURS_RE.search(inner_text)
    if status_hours_match:
        business_status = status_hours_match.group(1).strip()
        hours_text = status_hours_match.group(2).strip()
        if hours_text and "⋅" in hours_text: # Check for the separator
            hours = hours_text.split("⋅")[-1].strip().replace("\u202f", " ")
        elif hours_text:
            hours = hours_text.replace("\u202f", " ")
        if debug: logger.debug(f"Extracted Business_Status/Hours (innerText): {business_status} {hours}")
    else:
        # Fallback to HTML selectors
        status_hours_element = soup.find("span", string=re.compile(r"(Open|Closed|Closes)", re.IGNORECASE))
        if status_hours_element:
            full_text = status_hours_element.text.strip()
            if "Open" in full_text or "Closed" in full_text:
                business_status = full_text.split("⋅")[0].strip()
                if debug: logger.debug(f"Extracted Business_Status (HTML fallback): {business_status}")
            if "Closes" in full_text or ("Open" in full_text and ("PM" in full_text or "AM" in full_text)):
                hours_match = HOURS_RE.search(full_text)
                if hours_match:
                    hours = hours_match.group(1).strip()
                else:
                    hours = full_text
                if debug: logger.debug(f"Extracted Hours (HTML fallback): {hours}")
        if not business_status and not hours:
            if debug: logger.debug("Business Status and Hours elements not found from innerText or HTML fallback.")

    return {"Business_Status": business_status, "Hours": hours}