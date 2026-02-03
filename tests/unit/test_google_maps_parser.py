import pytest
from pathlib import Path
from bs4 import BeautifulSoup
from cocli.scrapers.google_maps_gmb_parser import parse_gmb_page
from cocli.scrapers.google_maps_parser import parse_business_listing_html
from cocli.core.text_utils import slugify

GOLDEN_SET_PATH = Path("tests/data/maps.google.com/golden_set.usv")
SNAPSHOT_DIR = Path("tests/data/maps.google.com/snapshots")

def get_golden_data():
    if not GOLDEN_SET_PATH.exists():
        return []
    
    test_cases = []
    with open(GOLDEN_SET_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            parts = line.strip().split("\x1f")
            if len(parts) >= 8:
                test_cases.append({
                    "name": parts[0],
                    "address": parts[1],
                    "phone": parts[2],
                    "website": parts[3],
                    "place_id": parts[4],
                    "search_phrase": parts[5],
                    "slug": slugify(parts[0])
                })
    return test_cases

@pytest.mark.parametrize("expected", get_golden_data())
def test_detail_parser_against_snapshots(expected):
    """Test the 'gm-details' parser against item.html snapshots."""
    snapshot_path = SNAPSHOT_DIR / expected["slug"] / "item.html"
    if not snapshot_path.exists():
        pytest.skip(f"Snapshot missing for {expected['name']}")
    
    html = snapshot_path.read_text(encoding="utf-8")
    parsed = parse_gmb_page(html)
    
    # Check Name
    assert parsed.get("Name") == expected["name"], f"Detail Name mismatch for {expected['slug']}"
    
    # Check Phone (if available in both)
    if expected["phone"] and parsed.get("Phone"):
        # Strip formatting for comparison
        clean_exp = "".join(filter(str.isdigit, expected["phone"]))
        clean_got = "".join(filter(str.isdigit, parsed["Phone"]))
        assert clean_exp in clean_got or clean_got in clean_exp

@pytest.mark.parametrize("expected", get_golden_data())
def test_list_parser_against_snapshots(expected):
    """Test the 'gm-list' parser against list.html snapshots."""
    snapshot_path = SNAPSHOT_DIR / expected["slug"] / "list.html"
    if not snapshot_path.exists():
        pytest.skip(f"Snapshot missing for {expected['name']}")
    
    html = snapshot_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    
    # Find all listing divs (divs inside the feed or articles)
    listing_divs = soup.find_all("div", {"role": "article"})
    
    if not listing_divs:
        # Fallback to older feed structure if article role is missing
        feed = soup.find("div", {"role": "feed"})
        if feed:
            listing_divs = feed.find_all("div", recursive=False)
            
    assert listing_divs, f"Could not find any business results in list.html for {expected['slug']}"
    
    found = False
    for div in listing_divs:
        div_html = str(div)
        # Only parse if it looks like a business (contains a link)
        if "href" not in div_html:
            continue
        
        parsed = parse_business_listing_html(div_html, expected["search_phrase"])
        
        # If we found our target Place ID or Name, validate it
        if parsed.get("Place_ID") == expected["place_id"] or parsed.get("Name") == expected["name"]:
            found = True
            assert parsed.get("Name") == expected["name"], f"List Name mismatch for {expected['slug']}"
            assert parsed.get("Place_ID") == expected["place_id"], f"List Place ID mismatch for {expected['slug']}"
            break
            
    assert found, f"Target {expected['name']} not found in search results list for {expected['slug']}"