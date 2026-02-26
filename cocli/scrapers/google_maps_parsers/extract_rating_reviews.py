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

    # --- 1. JSACTION SCAN (User Provided) ---
    # Specifically target the review chart container
    chart_container = soup.find(attrs={"jsaction": re.compile(r"reviewChart\.moreReviews")})
    if chart_container:
        text = chart_container.get_text(separator=" ", strip=True)
        # Look for "3.7" and "3 reviews"
        r_match = re.search(r"(\d\.\d)", text)
        if r_match:
            rating = r_match.group(1)
        
        c_match = re.search(r"([\d,]+)\s*Reviews", text, re.IGNORECASE)
        if c_match:
            reviews_count = c_match.group(1).replace(",", "")

    # --- 2. BREAKDOWN TABLE SCAN ---
    # Look for "5 stars, 2 reviews" in aria-labels
    if not reviews_count:
        breakdown_els = soup.find_all(attrs={"role": "img", "aria-label": re.compile(r"stars,")})
        total_from_breakdown = 0
        found_breakdown = False
        for el in breakdown_els:
            label_val = el.get("aria-label")
            if not label_val:
                continue
            label = str(label_val)
            # Example: "5 stars, 2 reviews"
            b_match = re.search(r"stars,\s*([\d,]+)\s*review", label, re.IGNORECASE)
            if b_match:
                found_breakdown = True
                total_from_breakdown += int(b_match.group(1).replace(",", ""))
        
        if found_breakdown:
            reviews_count = str(total_from_breakdown)

    # --- 3. SCAN ALL ARIA-LABELS AND TITLES ---
    for el in soup.find_all(True):
        label_val = el.get('aria-label') or el.get('title')
        if not label_val:
            continue
        label = str(label_val)
        
        if not rating:
            r_match = RATING_STRICT_RE.search(label)
            if r_match:
                rating = r_match.group(1)
            
        if not reviews_count:
            c_match = REVIEWS_STRICT_RE.search(label)
            if c_match:
                reviews_count = c_match.group(1).replace(",", "")

    # 2. SCAN ALL TEXT NODES AND CONTAINERS FOR "REVIEWS"
    if not reviews_count:
        # Search for elements whose text matches "[\d,]+ reviews"
        # We use soup.find_all(string=...) but also check parent's text 
        # in case Google splits the number and the word.
        
        # 2a. Direct string match
        review_nodes = soup.find_all(string=re.compile(r"[\d,]+\s*reviews", re.IGNORECASE))
        for node in review_nodes:
            match = re.search(r"([\d,]+)", node)
            if match:
                reviews_count = match.group(1).replace(",", "")
                break
        
        # 2b. Container text match (if 2a failed)
        if not reviews_count:
            # Look for any element that has "reviews" in its text and contains a number
            for tag in soup.find_all(["span", "button", "div"]):
                text = tag.get_text(separator=" ", strip=True)
                if "reviews" in text.lower():
                    # Look for the review pattern in the combined text
                    match = re.search(r"([\d,]+)\s*Reviews", text, re.IGNORECASE)
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
