# POLICY: frictionless-data-policy-enforcement
import os
import logging
from pathlib import Path
from bs4 import BeautifulSoup
from cocli.scrapers.google_maps_parsers.extract_rating_reviews import extract_rating_reviews

def audit_restored():
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    raw_dir = Path("data/campaigns/roadmap/raw/gm-list")
    files = list(raw_dir.rglob("*.html"))
    print(f"Auditing {len(files)} restored witness files...")
    
    for f in files:
        with open(f, "r", encoding="utf-8") as fh:
            html = fh.read()
        
        soup = BeautifulSoup(html, "html.parser")
        inner_text = soup.get_text(separator="\n", strip=True)
        
        # We also need to see if a phone number exists to correlate with area code
        phone = ""
        phone_match = re.search(r"\((\d{3})\)\s*\d{3}-\d{4}", inner_text)
        if phone_match:
            phone = phone_match.group(1)

        result = extract_rating_reviews(soup, inner_text, debug=True)
        
        revs = result["Reviews_count"]
        rating = result["Average_rating"]
        
        status = "[OK]"
        if revs == phone and revs != "":
            status = "[!! AREA CODE MATCH !!]"
        
        print(f"{status} {f.name}: Rating={rating}, Reviews={revs}, AreaCode={phone}")

if __name__ == "__main__":
    import re
    audit_restored()
