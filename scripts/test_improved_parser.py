import os
import sys
from bs4 import BeautifulSoup

sys.path.append(os.getcwd())

from cocli.scrapers.google.google_maps_parsers.extract_rating_reviews_gm_details import extract_rating_reviews_gm_details

def test_on_saved_files() -> None:
    for name in ["granite", "griffith", "final"]:
        path = ".logs/repro_" + name + ".html"
        if name == "final":
            path = ".logs/debug_final.html"
            
        if not os.path.exists(path):
            continue
            
        print("Testing: " + path)
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
        
        soup = BeautifulSoup(html, "html.parser")
        inner_text = soup.get_text(separator="\n", strip=True)
        
        result = extract_rating_reviews_gm_details(soup, inner_text, debug=True)
        print("RESULT: " + str(result))

if __name__ == "__main__":
    test_on_saved_files()
