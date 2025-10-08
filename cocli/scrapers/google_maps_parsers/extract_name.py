import re
from bs4 import BeautifulSoup
from typing import Optional

def extract_name(soup: BeautifulSoup, inner_text: str, debug: bool = False) -> str:
    """
    Extracts the business name from the aria-label of the main link, or falls back to other methods.
    """
    name = ""
    # First, try to get the name from the aria-label of the main link
    link = soup.find('a', class_='hfpxzc')
    if link and link.get('aria-label'):
        # The aria-label might contain extra text like '· Visited link', remove it
        name = link['aria-label'].split('·')[0].strip()
        if debug: print(f"Debug: Extracted Name (aria-label): {name}")
        return name

    # Fallback to innerText parsing
    name_match = re.search(r"^(.*?)\n", inner_text)
    if name_match:
        name = name_match.group(1).strip()
        if debug: print(f"Debug: Extracted Name (innerText): {name}")
    else:
        # Fallback to HTML selector if innerText parsing fails
        name_element = soup.find(class_=re.compile(r"fontHeadlineSmall"))
        if name_element:
            name = name_element.text.strip()
            if debug: print(f"Debug: Extracted Name (HTML fallback): {name}")
        else:
            if debug: print("Debug: Name element not found.")
    return name