from cocli.scrapers.google.gm_scraper.utils import get_tile_bounds

def test_get_tile_bounds_positive():
    bounds = get_tile_bounds("29.1_-98.4")
    assert bounds["lat_min"] == 29.1
    assert bounds["lat_max"] == 29.2
    assert bounds["lon_min"] == -98.4
    assert bounds["lon_max"] == -98.3

def test_get_tile_bounds_negative_lat():
    bounds = get_tile_bounds("-34.5_150.1")
    assert bounds["lat_min"] == -34.5
    assert bounds["lat_max"] == -34.4
    assert bounds["lon_min"] == 150.1
    assert bounds["lon_max"] == 150.2

def test_get_tile_bounds_invalid():
    assert get_tile_bounds("invalid") == {}
    assert get_tile_bounds("29.1") == {}
