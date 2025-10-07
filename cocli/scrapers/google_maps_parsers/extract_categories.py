import re
from typing import Dict, Any
from bs4 import BeautifulSoup

def extract_categories(soup: BeautifulSoup, inner_text: str, debug: bool = False) -> Dict[str, Any]:
    """
    Extracts category data from the BeautifulSoup object and inner text.
    """
    categories: Dict[str, Any] = {
        "First_category": "",
        "Second_category": "",
    }

    # The category is often a distinct line in the innerText
    # Look for a capitalized word sequence that doesn't look like a rating or review count
    # and is not "Open" or "Closes"
    category_match = re.search(
        r"(?<!\d\.\d\s)\b([A-Z][a-zA-Z\s]+?)\b(?!\s*\(\d+\)|\s*Open|\s*Closes)",
        inner_text
    )
    if category_match:
        potential_category = category_match.group(1).strip()
        # Final check to ensure it's not a rating/review count or other unwanted text
        if not re.match(r"^\d+\.?\d*$", potential_category) and \
           not re.match(r"^\(\d+\)$", potential_category) and \
           not re.match(r"^\d+\.?\d*\(\d+\)$", potential_category) and \
           potential_category != "·" and \
           potential_category != "" and \
           potential_category != "Open" and \
           potential_category != "Closes":
            categories["First_category"] = potential_category

    return categories