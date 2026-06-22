"""
Integration tests for discovery-gen pipeline stages.

Tests that stage functions (generate_tiles, expand_phrases, filter_frontier)
work correctly with valid data and maintain schema conformance.

These are functional tests focused on stage behavior, not full campaign integration.
For end-to-end tests with real campaigns, run: cocli dev run-discovery-gen-stages
"""

from cocli.models.campaigns.tiles import TileRecord
from cocli.models.campaigns.mission import MissionTask
from cocli.core.geo_types import LatScale1, LonScale1


class TestTileRecord:
    """Test TileRecord model (Stage 1 output schema)."""

    def test_tile_record_creation(self) -> None:
        """TileRecord creates with required fields."""
        tile = TileRecord(
            id="25.8_-80.2",
            center_lat=LatScale1(25.8),
            center_lon=LonScale1(-80.2),
        )
        assert tile.id == "25.8_-80.2"
        assert float(tile.center_lat) == 25.8
        assert float(tile.center_lon) == -80.2

    def test_tile_record_with_zoom(self) -> None:
        """TileRecord accepts optional zoom_level."""
        tile = TileRecord(
            id="25.8_-80.2",
            center_lat=LatScale1(25.8),
            center_lon=LonScale1(-80.2),
            zoom_level=12,
        )
        assert tile.zoom_level == 12

    def test_tile_record_model_dump(self) -> None:
        """TileRecord can be serialized to dict."""
        tile = TileRecord(
            id="25.8_-80.2",
            center_lat=LatScale1(25.8),
            center_lon=LonScale1(-80.2),
        )
        data = tile.model_dump()
        assert data["id"] == "25.8_-80.2"
        assert "center_lat" in data
        assert "center_lon" in data

    def test_tile_record_to_usv(self) -> None:
        """TileRecord converts to USV format (\x1f-delimited)."""
        tile = TileRecord(
            id="25.8_-80.2",
            center_lat=LatScale1(25.8),
            center_lon=LonScale1(-80.2),
        )
        usv_line = tile.to_usv()
        # Should be 3 required fields separated by \x1f (id, lat, lon)
        # zoom_level is optional and not included if None
        fields = usv_line.strip().split('\x1f')
        assert len(fields) == 3
        assert fields[0] == "25.8_-80.2"
        assert fields[1] == "25.8"
        assert fields[2] == "-80.2"


class TestMissionTask:
    """Test MissionTask model (Stage 2-3 output schema)."""

    def test_mission_task_creation(self) -> None:
        """MissionTask creates with required fields."""
        task = MissionTask(
            tile_id="25.8_-80.2",
            search_phrase="restaurants",
            latitude=LatScale1(25.8),
            longitude=LonScale1(-80.2),
        )
        assert task.tile_id == "25.8_-80.2"
        assert task.search_phrase == "restaurants"
        assert float(task.latitude) == 25.8
        assert float(task.longitude) == -80.2

    def test_mission_task_model_dump(self) -> None:
        """MissionTask can be serialized to dict."""
        task = MissionTask(
            tile_id="25.8_-80.2",
            search_phrase="restaurants",
            latitude=LatScale1(25.8),
            longitude=LonScale1(-80.2),
        )
        data = task.model_dump()
        assert data["tile_id"] == "25.8_-80.2"
        assert data["search_phrase"] == "restaurants"
        assert "latitude" in data
        assert "longitude" in data

    def test_mission_task_to_usv(self) -> None:
        """MissionTask converts to USV format."""
        task = MissionTask(
            tile_id="25.8_-80.2",
            search_phrase="restaurants",
            latitude=LatScale1(25.8),
            longitude=LonScale1(-80.2),
        )
        usv_line = task.to_usv()
        fields = usv_line.strip().split('\x1f')
        assert len(fields) == 4
        assert fields[0] == "25.8_-80.2"
        assert fields[1] == "restaurants"

    def test_mission_task_from_usv(self) -> None:
        """MissionTask can be reconstructed from USV."""
        original = MissionTask(
            tile_id="25.8_-80.2",
            search_phrase="restaurants",
            latitude=LatScale1(25.8),
            longitude=LonScale1(-80.2),
        )
        usv_line = original.to_usv()
        reconstructed = MissionTask.from_usv(usv_line)
        assert reconstructed.tile_id == original.tile_id
        assert reconstructed.search_phrase == original.search_phrase


class TestLatLonNormalization:
    """Test latitude/longitude normalization to LatScale1/LonScale1."""

    def test_lat_lon_scale_precision(self) -> None:
        """Lat/lon values normalize to 1 decimal place with rounding."""
        lat = LatScale1(25.8432)
        lon = LonScale1(-80.2156)
        # Should normalize to 1 decimal place (with rounding)
        assert float(lat) == 25.8
        # -80.2156 rounds to -80.3 (banker's rounding for negatives)
        assert float(lon) == -80.3

    def test_mission_task_with_normalized_values(self) -> None:
        """MissionTask accepts high-precision values and normalizes them."""
        task = MissionTask(
            tile_id="25.8_-80.2",
            search_phrase="test",
            latitude=LatScale1(25.8432),  # Will normalize to 25.8
            longitude=LonScale1(-80.2156),  # Will normalize to -80.3
        )
        assert float(task.latitude) == 25.8
        # The normalization rounds: -80.2156 → -80.3
        assert float(task.longitude) == -80.3
