# POLICY: frictionless-data-policy-enforcement
from bs4 import BeautifulSoup
from pathlib import Path

def inspect_html_witnesses(directory: str) -> None:
    root = Path(directory)
    for html_file in root.rglob("*.html"):
        print(f"--- File: {html_file} ---")
        with open(html_file, "r", encoding="utf-8") as f:
            html = f.read()
        
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" | ", strip=True)
        print(f"TEXT: {text}")
        
        # Look for stars/ratings
        stars = soup.find_all(attrs={"aria-label": True})
        for s in stars:
            label = str(s.get("aria-label", ""))
            if "stars" in label or "reviews" in label:
                print(f"  [ARIA] {label}")

if __name__ == "__main__":
    inspect_html_witnesses("data/campaigns/roadmap/raw/gm-list")
