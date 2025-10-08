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

    lines = inner_text.split('\n')
    use_next_line = False
    # Find the line that is likely the category
    # It's usually after the rating and reviews, and is not a number or contains digits.
    for line in lines:
        line = line.strip()
        if use_next_line:
            categories["First_category"] = line
            break
        if re.match(r"^\(\d*\)$", line):
            use_next_line = True

    if debug: print(f"Debug: Extracted categories: {categories}")
    return categories