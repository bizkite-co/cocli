# POLICY: frictionless-data-policy-enforcement
import re
from bs4 import BeautifulSoup
from typing import Dict
import logging

logger = logging.getLogger(__name__)

# Specialized patterns for the List (Search Results) view
# We use a broad regex on the raw HTML as a safety net for early captures
COMBO_ARIA_RE = re.compile(r'aria-label="(\d\.\d)\s*stars?\s*([\d,]+)\s*Reviews?"', re.IGNORECASE)
LIST_ARIA_RATING_RE = re.compile(r"(\d\.\d)\s*stars?", re.IGNORECASE)
LIST_ARIA_REVIEWS_RE = re.compile(r"([\d,]+)\s*Reviews?", re.IGNORECASE)

def extract_rating_reviews_gm_list(soup: BeautifulSoup, inner_text: str, debug: bool = False) -> Dict[str, str]:
    """
    Specialized extraction for Google Maps SEARCH RESULTS (List View).
    Prioritizes combined semantic ARIA labels.
    """
    rating = ""
    reviews_count = ""

    # 1. PRIMARY: RAW HTML SCAN (Most Robust against hydration issues)
    # Search the entire string representation for the combined label
    html_str = str(soup)
    combo_match = COMBO_ARIA_RE.search(html_str)
    if combo_match:
        rating = combo_match.group(1)
        reviews_count = combo_match.group(2).replace(",", "")
        if debug:
            logger.info(f"GM List Success (Raw Combo): {rating}, {reviews_count}")
        return {"Average_rating": rating, "Reviews_count": reviews_count}

    # 2. SECONDARY: BeautifulSoup ARIA Scan
    listing_elements = soup.find_all(attrs={"aria-label": True})
    for el in listing_elements:
        label = str(el.get("aria-label", ""))
        
        # Check for combined label in individual elements
        if "stars" in label.lower() and "review" in label.lower():
            r_match = LIST_ARIA_RATING_RE.search(label)
            rv_match = LIST_ARIA_REVIEWS_RE.search(label)
            if r_match:
                rating = r_match.group(1)
            if rv_match:
                reviews_count = rv_match.group(1).replace(",", "")
            
            if rating and reviews_count:
                if debug:
                    logger.info(f"GM List Success (Element ARIA): {rating}, {reviews_count}")
                return {"Average_rating": rating, "Reviews_count": reviews_count}

    # 3. TERTIARY: Split labels or InnerText fallback
    if not rating or not reviews_count:
        for el in listing_elements:
            label = str(el.get("aria-label", ""))
            if not rating:
                r_match = LIST_ARIA_RATING_RE.search(label)
                if r_match:
                    rating = r_match.group(1)
            if not reviews_count:
                rv_match = LIST_ARIA_REVIEWS_RE.search(label)
                if rv_match:
                    reviews_count = rv_match.group(1).replace(",", "")

    if not reviews_count and rating:
        prox_pattern = re.compile(re.escape(rating) + r"\s*\(([\d,]+)\)")
        match = prox_pattern.search(inner_text)
        if match:
            reviews_count = match.group(1).replace(",", "")

    return {"Average_rating": rating, "Reviews_count": reviews_count}
