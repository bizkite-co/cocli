import re
from bs4 import BeautifulSoup
from typing import Dict
import logging

logger = logging.getLogger(__name__)

# Strict patterns to avoid false positives (like phone numbers)
STRICT_RATING_RE = re.compile(r"(\d\.\d)\s*stars?", re.IGNORECASE)
STRICT_REVIEWS_RE = re.compile(r"([\d,]+)\s*Reviews?", re.IGNORECASE)
PROXIMITY_REVIEWS_RE = re.compile(r"\((\d+)\)")

def extract_rating_reviews(soup: BeautifulSoup, inner_text: str, debug: bool = False) -> Dict[str, str]:
    """
    BULLETPROOF extraction of rating and reviews.
    Layers: JSACTION -> BREAKDOWN -> ARIA -> TEXT -> PROXIMITY
    """
    rating = ""
    reviews_count = ""

    # 1. JSACTION SCAN (Specifically the review chart)
    chart = soup.find(attrs={"jsaction": re.compile(r"reviewChart\.moreReviews")})
    if chart:
        text = chart.get_text(separator=" ", strip=True)
        r_match = re.search(r"(\d\.\d)", text)
        if r_match:
            rating = r_match.group(1)
        
        c_match = STRICT_REVIEWS_RE.search(text)
        if c_match:
            reviews_count = c_match.group(1).replace(",", "")

    # 2. BREAKDOWN TABLE AGGREGATION
    if not reviews_count:
        # Search for "5 stars, 2 reviews" style labels
        breakdown = soup.find_all(attrs={"aria-label": re.compile(r"stars,")})
        total = 0
        found = False
        for el in breakdown:
            label = str(el.get("aria-label", ""))
            match = re.search(r"stars,\s*([\d,]+)\s*review", label, re.IGNORECASE)
            if match:
                found = True
                total += int(match.group(1).replace(",", ""))
        if found:
            reviews_count = str(total)

    # 3. GLOBAL ARIA & TITLE SCAN
    for el in soup.find_all(True):
        label_val = el.get('aria-label') or el.get('title')
        if not label_val:
            continue
        label = str(label_val)
        
        if not rating:
            r_match = STRICT_RATING_RE.search(label)
            if r_match:
                rating = r_match.group(1)
            
        if not reviews_count:
            c_match = STRICT_REVIEWS_RE.search(label)
            if c_match:
                reviews_count = c_match.group(1).replace(",", "")

    # 4. TEXT NODE SCAN
    if not reviews_count:
        # Global search for "X reviews" in text nodes
        nodes = soup.find_all(string=re.compile(r"[\d,]+\s*Reviews?", re.IGNORECASE))
        for node in nodes:
            match = re.search(r"([\d,]+)", node)
            if match:
                reviews_count = match.group(1).replace(",", "")
                break

    # 5. PROXIMITY FALLBACK (Inner Text)
    if not rating:
        r_match = STRICT_RATING_RE.search(inner_text)
        if r_match:
            rating = r_match.group(1)
        
    if not reviews_count and rating:
        # Look for "(3)" within 50 chars of the rating
        # Dot-all to match across line breaks
        pattern = re.compile(re.escape(rating) + r"[\s\S]{0,50}\(([\d,]+)\)")
        match = pattern.search(inner_text)
        if match:
            reviews_count = match.group(1).replace(",", "")

    if debug:
        logger.debug(f"Extracted Rating: {rating}, Reviews: {reviews_count}")

    return {"Average_rating": rating, "Reviews_count": reviews_count}
