import os
import sys
from typing import List, Dict, Any
from bs4 import BeautifulSoup

# Ensure we can import from cocli
sys.path.append(os.getcwd())

from cocli.scrapers.google.google_maps_parsers.extract_rating_reviews_gm_details import extract_rating_reviews_gm_details

TEST_CASES: List[Dict[str, Any]] = [
    {
        "name": "Granite Snippet (Multi-Review)",
        "html": """<div jsaction="reviewChart.moreReviews"><span>3.7</span><span>3 reviews</span></div>""",
        "expected": {"rating": "3.7", "reviews": "3"}
    },
    {
        "name": "Single Review Case",
        "html": """<div jsaction="reviewChart.moreReviews"><span>5.0</span><span>1 review</span></div>""",
        "expected": {"rating": "5.0", "reviews": "1"}
    },
    {
        "name": "Breakdown Table Case",
        "html": """
            <tr aria-label="5 stars, 10 reviews"></tr>
            <tr aria-label="4 stars, 5 reviews"></tr>
        """,
        "expected": {"rating": "", "reviews": "15"}
    },
    {
        "name": "ARIA Label Case",
        "html": """<span aria-label="4.7 stars 17,452 Reviews"></span>""",
        "expected": {"rating": "4.7", "reviews": "17452"}
    }
]

def run_tests() -> None:
    from typing import cast
    print("--- Running Parser Regression Suite ---")
    for case in TEST_CASES:
        soup = BeautifulSoup(str(case["html"]), "html.parser")
        result = extract_rating_reviews_gm_details(soup, "", debug=False)
        
        expected = cast(Dict[str, str], case["expected"])
        rating_match = result["Average_rating"] == expected["rating"]
        reviews_match = result["Reviews_count"] == expected["reviews"]
        
        status = "✅" if rating_match and reviews_match else "❌"
        print(f"{status} {case['name']}")
        if not rating_match or not reviews_match:
            print(f"   Expected: {expected}")
            print(f"   Got:      {result}")

    # Also test against saved files if they exist
    files = ["repro_granite.html", "repro_griffith.html", "debug_final.html"]
    for fname in files:
        path = ".logs/" + fname
        if os.path.exists(path):
            print(f"\n--- Testing File: {path} ---")
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()
            soup = BeautifulSoup(html, "html.parser")
            result = extract_rating_reviews_gm_details(soup, soup.get_text(separator=" "), debug=False)
            print(f"   Result: {result}")

if __name__ == "__main__":
    run_tests()
