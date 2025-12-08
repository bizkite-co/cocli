from cocli.core.scrape_index import ScrapeIndex, ScrapedArea, _calculate_overlap_area
from datetime import datetime, timedelta
from pathlib import Path
import pytest

@pytest.fixture
def temp_scrape_index_dir(tmp_path: Path, mocker):
    """Fixture to set up a temporary directory for scrape index files."""
    index_dir = tmp_path / "indexes" / "scraped_areas"
    index_dir.mkdir(parents=True, exist_ok=True)
    mocker.patch("cocli.core.scrape_index.get_scraped_areas_index_dir", return_value=index_dir)
    return index_dir

@pytest.fixture
def scrape_index_instance(temp_scrape_index_dir):
    """Fixture to provide an instance of ScrapeIndex with a temporary directory."""
    return ScrapeIndex()

def test_calculate_overlap_area():
    # Test case 1: Full overlap (identical rectangles)
    bounds1 = {'lat_min': 10.0, 'lat_max': 20.0, 'lon_min': 30.0, 'lon_max': 40.0}
    bounds2 = {'lat_min': 10.0, 'lat_max': 20.0, 'lon_min': 30.0, 'lon_max': 40.0}
    expected_overlap = (20.0 - 10.0) * (40.0 - 30.0) # 10 * 10 = 100
    assert _calculate_overlap_area(bounds1, bounds2) == pytest.approx(expected_overlap)

    # Test case 2: Partial overlap
    bounds1 = {'lat_min': 10.0, 'lat_max': 20.0, 'lon_min': 30.0, 'lon_max': 40.0}
    bounds2 = {'lat_min': 15.0, 'lat_max': 25.0, 'lon_min': 35.0, 'lon_max': 45.0}
    expected_overlap = (20.0 - 15.0) * (40.0 - 35.0) # 5 * 5 = 25
    assert _calculate_overlap_area(bounds1, bounds2) == pytest.approx(expected_overlap)

    # Test case 3: No overlap (rectangles are separate)
    bounds1 = {'lat_min': 10.0, 'lat_max': 20.0, 'lon_min': 30.0, 'lon_max': 40.0}
    bounds2 = {'lat_min': 21.0, 'lat_max': 30.0, 'lon_min': 41.0, 'lon_max': 50.0}
    assert _calculate_overlap_area(bounds1, bounds2) == 0.0

    # Test case 4: No overlap (rectangles touch at a corner)
    bounds1 = {'lat_min': 10.0, 'lat_max': 20.0, 'lon_min': 30.0, 'lon_max': 40.0}
    bounds2 = {'lat_min': 20.0, 'lat_max': 30.0, 'lon_min': 40.0, 'lon_max': 50.0}
    assert _calculate_overlap_area(bounds1, bounds2) == 0.0

    # Test case 5: One rectangle fully contained within another
    bounds1 = {'lat_min': 10.0, 'lat_max': 30.0, 'lon_min': 30.0, 'lon_max': 50.0}
    bounds2 = {'lat_min': 15.0, 'lat_max': 25.0, 'lon_min': 35.0, 'lon_max': 45.0}
    expected_overlap = (25.0 - 15.0) * (45.0 - 35.0) # 10 * 10 = 100
    assert _calculate_overlap_area(bounds1, bounds2) == pytest.approx(expected_overlap)

    # Test case 6: Rectangles overlap on one axis only (e.g., vertical strip)
    bounds1 = {'lat_min': 10.0, 'lat_max': 20.0, 'lon_min': 30.0, 'lon_max': 40.0}
    bounds2 = {'lat_min': 15.0, 'lat_max': 18.0, 'lon_min': 30.0, 'lon_max': 40.0}
    expected_overlap = (18.0 - 15.0) * (40.0 - 30.0) # 3 * 10 = 30
    assert _calculate_overlap_area(bounds1, bounds2) == pytest.approx(expected_overlap)
