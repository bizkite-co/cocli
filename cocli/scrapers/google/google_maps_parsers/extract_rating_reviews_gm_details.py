import re
from bs4 import BeautifulSoup
from typing import Dict
import logging

logger = logging.getLogger(__name__)

# Strict patterns to avoid false positives (like phone numbers)
STRICT_RATING_RE = re.compile(r"(\d\.\d)\s*stars?", re.IGNORECASE)
STRICT_REVIEWS_RE = re.compile(r"([\d,]+)\s*Reviews?", re.IGNORECASE)
PROXIMITY_REVIEWS_RE = re.compile(r"\((\d+)\)")

def extract_rating_reviews_gm_details(soup: BeautifulSoup, inner_text: str, debug: bool = False) -> Dict[str, str]:
    """
    ULTRA-ROBUST extraction based on verified Google Maps summary snippet.
    """
    rating = ""
    reviews_count = ""

    # 1. PRIMARY: Targeted Summary Block (jsaction containing reviewChart.moreReviews)
    chart_summary = soup.find(attrs={"jsaction": re.compile(r"reviewChart\.moreReviews")})
    if chart_summary:
        # Rating is often in fontDisplayLarge
        rating_el = chart_summary.find(class_="fontDisplayLarge")
        if rating_el:
            rating = rating_el.get_text(strip=True)
        
        # Total Reviews is often in a span/button inside this block
        # Look for "X reviews" or "X opinions"
        total_match = re.search(r"([\d,]+)\s*(?:Reviews?|Opinions?)", chart_summary.get_text(separator=" ", strip=True), re.IGNORECASE)
        if total_match:
            reviews_count = total_match.group(1).replace(",", "")

    # 2. SECONDARY: Breakdown Table Summation (Extremely reliable for 'Gold' views)
    # Snippet: <tr class="BHOKXe" role="img" aria-label="5 stars, 13,894 reviews">
    if not reviews_count:
        breakdown_rows = soup.find_all(attrs={"aria-label": re.compile(r"stars,.*reviews?", re.IGNORECASE)})
        if breakdown_rows:
            total = 0
            for row in breakdown_rows:
                label = str(row.get("aria-label", ""))
                # Match: "5 stars, 13,894 reviews"
                match = re.search(r"stars,\s*([\d,]+)\s*review", label, re.IGNORECASE)
                if match:
                    total += int(match.group(1).replace(",", ""))
            if total > 0:
                reviews_count = str(total)

    # 3. FALLBACK: Global ARIA/Title scan for "X.X stars"
    if not rating:
        star_elements = soup.find_all(attrs={"aria-label": re.compile(r"^\d\.\d\s*stars?", re.IGNORECASE)})
        if star_elements:
            # Take the first one, usually the primary business rating
            label = str(star_elements[0].get("aria-label", ""))
            match = re.search(r"(\d\.\d)", label)
            if match:
                rating = match.group(1)

    # 4. FALLBACK: Text node scan for "X reviews"
    if not reviews_count:
        nodes = soup.find_all(string=re.compile(r"[\d,]+\s*(?:Reviews?|Opinions?)", re.IGNORECASE))
        for node in nodes:
            # Avoid long strings, look for short snippets like "17,059 reviews"
            if len(node) < 50:
                match = re.search(r"([\d,]+)", node)
                if match:
                    reviews_count = match.group(1).replace(",", "")
                    break

    # 5. FINAL: Proximity scan (Inner Text)
    if not rating:
        r_match = STRICT_RATING_RE.search(inner_text)
        if r_match:
            rating = r_match.group(1)
        
    if not reviews_count and rating:
        escaped_rating = re.escape(rating)
        # Look for "(17,059)" or "17,059 reviews" within 30 chars of the rating
        prox_pattern = re.compile(escaped_rating + r"[\s\S]{0,30}?\(?([\d,]+)\)?\s*(?:Reviews?|Opinions?)?", re.IGNORECASE)
        match = prox_pattern.search(inner_text)
        if match:
            reviews_count = match.group(1).replace(",", "")

    if debug:
        logger.debug(f"Extracted Rating: {rating}, Reviews: {reviews_count}")

    return {"Average_rating": rating, "Reviews_count": reviews_count}
