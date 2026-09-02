from __future__ import annotations
import re
from bs4 import BeautifulSoup
from typing import Optional
import logging

logger = logging.getLogger(__name__)

def extract_website(soup: BeautifulSoup, inner_text: str, debug: bool = False) -> dict[str, str]:
    """
    Extracts the website URL and domain from HTML or falls back to innerText.
    """
    website = ""
    domain = ""

    # Prioritize data-value="Website", then aria-label, then any http/https link not related to maps
    website_element = soup.find("a", attrs={"data-value": "Website"})
    if not website_element:
        # Fallback 1: data-item-id="authority" (Common in details view)
        website_element = soup.find("a", {"data-item-id": "authority"})
    
    if not website_element:
        # Fallback 2: aria-label containing "Website"
        def is_website_label(label: Optional[str]) -> bool:
            return bool(label and 'website' in label.lower())
        website_element = soup.find("a", attrs={"aria-label": is_website_label})

    if website_element and website_element.has_attr("href"):
        href_value = website_element["href"]
        website = str(href_value) # Ensure it's a string
        if debug:
            logger.debug(f"Extracted Website (HTML data-value): {website}")
    else:
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if isinstance(href, str) and (
                href.startswith("http")
                and "google.com/maps" not in href
                and "maps.google.com" not in href
                and re.search(r"\.(com|org|net|io|co|us|gov|edu)", href)
            ):
                website = href
                if debug:
                    logger.debug(f"Extracted Website (HTML generic link): {website}")
                break
        if not website:
            if debug:
                logger.debug("Website element not found from HTML.")

    if website:
        # Google's outbound website links often carry an rwg_token
        # redirect-tracking query string with no path segment before it
        # (e.g. https://example.com?rwg_token=...) - [^/]+ alone captured
        # the whole query string as the domain, blowing past the model's
        # 100-char cap and crashing (nacking) the entire scan task. Stop at
        # '/', '?', or '#' so only the host[:port] is kept.
        domain_match = re.search(r"https?://(?:www\.)?([^/?#]+)", website)
        if domain_match:
            domain = domain_match.group(1)
            if debug:
                logger.debug(f"Extracted Domain: {domain}")
        else:
            if debug:
                logger.debug("Debug: Domain not found in Website URL.")

    return {"Website": website, "Domain": domain}