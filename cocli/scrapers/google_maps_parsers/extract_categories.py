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
    category_element = soup.find("span", text=re.compile(r".*"))
    if category_element:
        categories["First_category"] = category_element.text.strip()

    return categories