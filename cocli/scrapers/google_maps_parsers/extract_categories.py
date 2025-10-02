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

    # The category is usually after the rating, e.g., "4.8(21)\nFlooring store"
    match = re.search(r"\d+\.\d+\(\d+\)\n(.*?)\n", inner_text)
    if match:
        categories["First_category"] = match.group(1).strip()

    return categories