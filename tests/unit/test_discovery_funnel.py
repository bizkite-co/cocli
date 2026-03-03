# POLICY: frictionless-data-policy-enforcement
import pytest
from cocli.core.geo_types import LatScale1, LonScale1, LatScale6
from cocli.core.sharding import get_grid_tile_id, get_geo_shard
from cocli.core.text_utils import slugify
from cocli.models.campaigns.mission import MissionTask

def test_tile_id_bucketing_logic():
    """
    Ensures that Scale1 (Tenths) always uses floor logic to define the 
    Southwest corner of a grid tile.
    """
    # Boundary: Just below the next tenth
    assert str(LatScale1(25.099999)) == "25.0"
    assert str(LonScale1(-79.900001)) == "-80.0" # Floor of -79.900001 is -80.0
    
    # Boundary: Exactly on the line
    assert str(LatScale1(25.1)) == "25.1"
    
    # Boundary: Just above the line
    assert str(LatScale1(25.100001)) == "25.1"

    # Full Tile ID check
    assert get_grid_tile_id(25.05, -79.95) == "25.0_-80.0"

def test_location_precision_logic():
    """
    Ensures that Scale6 (Points) uses rounding to preserve the nearest 
    high-fidelity coordinate.
    """
    # Should round up
    assert str(LatScale6(25.1234567)) == "25.123457"
    # Should round down
    assert str(LatScale6(25.1234564)) == "25.123456"

def test_sharding_ordinance():
    """
    Verifies that the top-level shard (first digit) remains consistent.
    """
    assert get_geo_shard(25.0) == "2"
    assert get_geo_shard(5.8) == "5"
    assert get_geo_shard(-12.3) == "-"

def test_mission_task_slugification_and_matching():
    """
    Tests the logic used in ScrapeIndex to ensure that spaces in mission 
    phrases match hyphenated slugs in the index.
    """
    mission_phrase = "financial advisor"
    index_phrase = "financial-advisor"
    
    # The actual code used in ScrapeIndex.is_tile_scraped
    assert slugify(mission_phrase) == index_phrase
    assert slugify(index_phrase) == index_phrase

def test_omap_path_structure():
    """
    Ensures that MissionTask correctly identifies its own sharded path components.
    """
    task = MissionTask(
        tile_id="25.0_-80.0",
        search_phrase="financial advisor",
        latitude=25.05,
        longitude=-80.05
    )
    
    # Component verification
    lat_shard = get_geo_shard(float(task.latitude))
    grid_parts = task.tile_id.split("_")
    
    assert lat_shard == "2"
    assert grid_parts[0] == "25.0"
    assert grid_parts[1] == "-80.0"
    assert slugify(task.search_phrase) == "financial-advisor"
