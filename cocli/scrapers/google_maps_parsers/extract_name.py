import re
from bs4 import BeautifulSoup
from typing import Optional

def extract_name(soup: BeautifulSoup, inner_text: str, debug: bool = False) -> str:
    """
    Extracts the business name from the innerText or falls back to HTML selectors.
    """
    name = ""
    # Name is usually the first line before a rating or other details
    name_match = re.search(r"^(.*?)(?:\n\d+\.\d+|\n[A-Z][a-z]+ \d+)", inner_text)
    if name_match:
        name = name_match.group(1).strip()
        if debug: print(f"Debug: Extracted Name (innerText): {name}")
    else:
        # Fallback to HTML selector if innerText parsing fails
        # Using a more generic selector for name
        name_element = soup.find("div", {"role": "heading", "aria-level": "2"})
        if name_element:
            name = name_element.text.strip()
            if debug: print(f"Debug: Extracted Name (HTML fallback): {name}")
        else:
            if debug: print("Debug: Name element not found from innerText or HTML fallback.")
    return name