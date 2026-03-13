# POLICY: frictionless-data-policy-enforcement
import logging
from pathlib import Path
from bs4 import BeautifulSoup
from cocli.scrapers.google.google_maps_parsers.extract_rating_reviews_gm_list import extract_rating_reviews_gm_list

def audit_restored() -> None:
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    raw_dir = Path("temp/tests/20260305_072115")
    files = list(raw_dir.rglob("*.html"))
    print(f"Auditing {len(files)} restored witness files...")
    
    for f in files:
        with open(f, "r", encoding="utf-8") as fh:
            html = fh.read()
        
        soup = BeautifulSoup(html, "html.parser")
        inner_text = soup.get_text(separator="\n", strip=True)
        
        # We also need to see if a phone number exists to correlate with area code
        phone = ""
        import re
        phone_match = re.search(r"\((\d{3})\)\s*\d{3}-\d{4}", inner_text)
        if phone_match:
            phone = phone_match.group(1)

        result = extract_rating_reviews_gm_list(soup, inner_text)
        
        # FIND THE RATING ELEMENT AND ITS GRANDPARENT FOR CONTEXT
        rating_el = soup.find(attrs={"aria-label": re.compile(r"^\d\.\d\s*stars?", re.IGNORECASE)})
        if rating_el:
            parent = rating_el.find_parent()
            if parent:
                grandparent = parent.find_parent()
                el_str = str(grandparent) if grandparent else str(parent)
            else:
                el_str = str(rating_el)
        else:
            el_str = "NOT FOUND"

        revs = result["Reviews_count"]
        rating = result["Average_rating"]
        
        status = "[OK]"
        if revs == phone and revs != "":
            status = "[!! AREA CODE MATCH !!]"
        
        print(f"{status} {f.name}: Rating={rating}, Reviews={revs}")
        if rating:
            print(f"  Element: {el_str}")

if __name__ == "__main__":
    audit_restored()
