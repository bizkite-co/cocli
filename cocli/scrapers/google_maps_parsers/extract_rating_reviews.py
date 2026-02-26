import re
from bs4 import BeautifulSoup
from typing import Dict
import logging

logger = logging.getLogger(__name__)

# Pattern for Griffith-style: "4.7 stars 17,452 Reviews"
# Pattern for Granite-style: "3.7\n(3)" or "3.7 (3)"
# We use a broad scan but keep it tied to keywords
RATING_STRICT_RE = re.compile(r"(\d\.\d)\s*stars?", re.IGNORECASE)
# This captures Y in "X.X stars Y Reviews" OR "Y Reviews"
REVIEWS_STRICT_RE = re.compile(r"(?:\d\.\d\s*stars\s+)?([\d,]+)\s*Reviews?", re.IGNORECASE)

def extract_rating_reviews(soup: BeautifulSoup, inner_text: str, debug: bool = False) -> Dict[str, str]:
    """
    ULTRA-ROBUST extraction of rating and reviews.
    Scans ARIA labels, titles, and all text nodes with strict proximity checks.
    """
    rating = ""
    reviews_count = ""

    # 1. SCAN ALL ARIA-LABELS AND TITLES (Highest Reliability)
    for el in soup.find_all(True):
        label = el.get('aria-label') or el.get('title')
        if not label:
            continue
        label = str(label)
        
        if not rating:
            r_match = RATING_STRICT_RE.search(label)
            if r_match:
                rating = r_match.group(1)
            
        if not reviews_count:
            c_match = REVIEWS_STRICT_RE.search(label)
            if c_match:
                reviews_count = c_match.group(1).replace(",", "")

    # 2. SCAN ALL TEXT NODES FOR "REVIEWS" (Direct search)
    if not reviews_count:
        # Look for any text node containing the word "reviews" with a preceding number
        review_nodes = soup.find_all(string=re.compile(r"[\d,]+\s*reviews", re.IGNORECASE))
        for node in review_nodes:
            match = re.search(r"([\d,]+)", node)
            if match:
                reviews_count = match.group(1).replace(",", "")
                break

    # 3. PROXIMITY FALLBACK: Look for (X) near the rating in innerText
    if not reviews_count and rating:
        # Look for the rating followed by a parenthesized number within 100 chars
        # Example: "3.7\n...\n(3)"
        escaped_rating = re.escape(rating)
        # Use a dot-all regex to scan across lines
        prox_pattern = re.compile(escaped_rating + r"[\s\S]{0,100}\(([\d,]+)\)")
        match = prox_pattern.search(inner_text)
        if match:
            reviews_count = match.group(1).replace(",", "")

    if debug:
        logger.debug(f"Extracted -> Rating: {rating}, Reviews: {reviews_count}")

    return {"Average_rating": rating, "Reviews_count": reviews_count}
