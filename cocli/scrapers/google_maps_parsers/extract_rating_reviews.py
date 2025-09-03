import re
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional

def extract_rating_reviews(soup: BeautifulSoup, inner_text: str, debug: bool = False) -> Dict[str, str]:
    """
    Extracts average rating and reviews count from innerText or falls back to HTML selectors.
    """
    rating = ""
    reviews_count = ""

    rating_reviews_match = re.search(r"(\d+\.\d+)\((\d+)\)", inner_text)
    if rating_reviews_match:
        rating = rating_reviews_match.group(1)
        reviews_count = rating_reviews_match.group(2)
        if debug: print(f"Debug: Extracted Rating/Reviews (innerText): {rating} ({reviews_count})")
    else:
        # Fallback to HTML selectors
        rating_element = soup.find("span", {"aria-label": re.compile(r"\d+\.\d+ stars")})
        if rating_element:
            rating = re.search(r"(\d+\.\d+)", rating_element["aria-label"]).group(1)
            if debug: print(f"Debug: Extracted Average_rating (HTML fallback): {rating}")
        reviews_count_element = soup.find("span", {"aria-label": re.compile(r"\d+ Reviews")})
        if reviews_count_element:
            reviews_count = re.search(r"(\d+)", reviews_count_element["aria-label"]).group(1)
            if debug: print(f"Debug: Extracted Reviews_count (HTML fallback): {reviews_count}")
        if not rating and not reviews_count:
            if debug: print("Debug: Rating/Reviews not found from innerText or HTML fallback.")

    return {"Average_rating": rating, "Reviews_count": reviews_count}
