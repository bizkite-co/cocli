import re
from bs4 import BeautifulSoup
from typing import Dict
import logging

logger = logging.getLogger(__name__)

RATING_REVIEWS_RE = re.compile(r"(\d+\.\d+)\s*\((\d+)\)")
RATING_RE = re.compile(r"(\d+\.\d+)")
REVIEWS_RE = re.compile(r"(\d+)")

def extract_rating_reviews(soup: BeautifulSoup, inner_text: str, debug: bool = False) -> Dict[str, str]:
    """
    Extracts average rating and reviews count from innerText or falls back to HTML selectors.
    """
    rating = ""
    reviews_count = ""

    rating_reviews_match = RATING_REVIEWS_RE.search(inner_text)
    if rating_reviews_match:
        rating = rating_reviews_match.group(1)
        reviews_count = rating_reviews_match.group(2)
        if debug:
            logger.debug(f"Extracted Rating/Reviews (innerText): {rating} ({reviews_count})")
    else:
        # Fallback to HTML selectors
        rating_element = soup.find("span", {"aria-label": re.compile(r"\d+\.\d+ stars")})
        if rating_element:
            rating_match = RATING_RE.search(str(rating_element["aria-label"]))
            if rating_match:
                rating = rating_match.group(1)
                if debug:
                    logger.debug(f"Extracted Average_rating (HTML fallback): {rating}")
        reviews_count_element = soup.find("span", {"aria-label": re.compile(r"\d+ Reviews")})
        if reviews_count_element:
            reviews_count_match = REVIEWS_RE.search(str(reviews_count_element["aria-label"]))
            if reviews_count_match:
                reviews_count = reviews_count_match.group(1)
                if debug:
                    logger.debug(f"Extracted Reviews_count (HTML fallback): {reviews_count}")
        if not rating and not reviews_count:
            if debug:
                logger.debug("Rating/Reviews not found from innerText or HTML fallback.")

    return {"Average_rating": rating, "Reviews_count": reviews_count}
