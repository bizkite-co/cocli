import csv
import pytest
from pathlib import Path
from cocli.scrapers.google.google_maps_parser import parse_business_listing_html

TEST_DATA_DIR = Path("tests/data/maps.google.com")
CASES = TEST_DATA_DIR / "field_extraction_cases.usv"


def load_cases():
    rows = []
    if not CASES.exists():
        return rows
    with CASES.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\x1f")
        for row in reader:
            place_id = row.get("place_id", "")
            if place_id.startswith("ChIJ"):
                rows.append((row["place_id"], row["field"], row["expected"], row["html_path"]))
    return rows


@pytest.mark.parametrize("place_id,field,expected,html_rel", load_cases())
def test_field_extraction(place_id, field, expected, html_rel):
    html_file = TEST_DATA_DIR / html_rel
    if not html_file.exists():
        pytest.skip(f"HTML file not found: {html_file}")
    html = html_file.read_text(encoding="utf-8")
    result = parse_business_listing_html(html, keyword="financial-advisor")
    actual = str(result.get(field.title(), ""))
    assert actual == expected, f"{place_id}: {field}: expected {expected!r}, got {actual!r}"
