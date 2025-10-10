import re
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

def extract_website(soup: BeautifulSoup, inner_text: str, debug: bool = False) -> Dict[str, str]:
    """
    Extracts the website URL and domain from HTML or falls back to innerText.
    """
    website = ""
    domain = ""

    # Prioritize data-value="Website", then any http/https link not related to maps
    website_element = soup.find("a", attrs={"data-value": "Website"})
    if website_element and website_element.has_attr("href"):
        website = website_element["href"]
        if debug: logger.debug(f"Extracted Website (HTML data-value): {website}")
    else:
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if (
                href.startswith("http")
                and "google.com/maps" not in href
                and "maps.google.com" not in href
                and re.search(r"\.(com|org|net|io|co|us|gov|edu)", href)
            ):
                website = href
                if debug: logger.debug(f"Extracted Website (HTML generic link): {website}")
                break
        if not website:
            if debug: logger.debug("Website element not found from HTML.")

    if website:
        domain_match = re.search(r"https?://(?:www\.)?([^/]+)", website)
        if domain_match:
            domain = domain_match.group(1)
            if debug: logger.debug(f"Extracted Domain: {domain}")
        else:
            if debug: logger.debug("Debug: Domain not found in Website URL.")

    return {"Website": website, "Domain": domain}