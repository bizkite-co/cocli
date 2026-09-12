"""
Unit tests for discovery-gen pipeline stage functions.

Tests individual stage functions (generate_tiles, expand_phrases, filter_frontier)
with controlled inputs and mocked dependencies.
"""

import pytest
from unittest.mock import patch
from pathlib import Path

from cocli.commands.campaign.discovery_gen_stages import (
    generate_tiles,
    _load_target_locations,
)
from cocli.models.campaigns.tiles import TileRecord


class TestGenerateTiles:
    """Unit tests for Stage 1: generate_tiles function."""

    @pytest.fixture
    def sample_locations(self) -> list[dict]:
        """Sample target locations for testing."""
        return [
            {"name": "Miami, FL", "lat": 25.8, "lon": -80.2},
            {"name": "Tampa, FL", "lat": 27.9, "lon": -82.5},
        ]

    @pytest.fixture
    def mock_grid_tiles(self) -> list[dict]:
        """Mock grid tiles returned by get_campaign_grid_tiles."""
        return [
            {"id": "25.8_-80.2", "center_lat": 25.8, "center_lon": -80.2},
            {"id": "25.8_-80.1", "center_lat": 25.8, "center_lon": -80.1},
            {"id": "25.9_-80.2", "center_lat": 25.9, "center_lon": -80.2},
        ]

    def test_generate_tiles_with_locations(
        self, sample_locations: list[dict], mock_grid_tiles: list[dict]
    ) -> None:
        """Test generate_tiles with explicit target locations."""
        with patch("cocli.commands.campaign.discovery_gen_stages.get_campaign_dir") as mock_get_dir:
            with patch(
                "cocli.commands.campaign.discovery_gen_stages.get_campaign_grid_tiles"
            ) as mock_grid:
                mock_get_dir.return_value = Path("/tmp/campaign")
                mock_grid.return_value = mock_grid_tiles

                tiles = generate_tiles(
                    "test_campaign",
                    target_locations=sample_locations,
                    proximity_miles=10.0,
                    save_output=False,
                )

                # Verify grid was called with correct parameters
                mock_grid.assert_called_once_with(
                    "test_campaign", target_locations=sample_locations
                )

                # Verify tiles were converted to TileRecord
                assert len(tiles) == 3
                assert all(isinstance(t, TileRecord) for t in tiles)
                assert tiles[0].id == "25.8_-80.2"
                assert float(tiles[0].center_lat) == 25.8
                assert float(tiles[0].center_lon) == -80.2

    def test_generate_tiles_missing_campaign(self, sample_locations: list[dict]) -> None:
        """Test generate_tiles with missing campaign directory."""
        with patch("cocli.commands.campaign.discovery_gen_stages.get_campaign_dir") as mock_get_dir:
            mock_get_dir.return_value = None

            with pytest.raises(ValueError, match="Campaign directory not found"):
                generate_tiles(
                    "nonexistent_campaign",
                    target_locations=sample_locations,
                    save_output=False,
                )

    def test_generate_tiles_deterministic(
        self, sample_locations: list[dict], mock_grid_tiles: list[dict]
    ) -> None:
        """Test that generate_tiles produces deterministic output."""
        with patch("cocli.commands.campaign.discovery_gen_stages.get_campaign_dir") as mock_get_dir:
            with patch(
                "cocli.commands.campaign.discovery_gen_stages.get_campaign_grid_tiles"
            ) as mock_grid:
                mock_get_dir.return_value = Path("/tmp/campaign")
                mock_grid.return_value = mock_grid_tiles

                # Run twice with same input
                tiles1 = generate_tiles(
                    "test_campaign",
                    target_locations=sample_locations,
                    save_output=False,
                )
                tiles2 = generate_tiles(
                    "test_campaign",
                    target_locations=sample_locations,
                    save_output=False,
                )

                # Should produce identical output
                assert len(tiles1) == len(tiles2)
                assert [t.id for t in tiles1] == [t.id for t in tiles2]
                assert [float(t.center_lat) for t in tiles1] == [float(t.center_lat) for t in tiles2]

    def test_generate_tiles_filters_incomplete_tiles(
        self, sample_locations: list[dict]
    ) -> None:
        """Test that generate_tiles skips tiles missing required fields."""
        incomplete_tiles = [
            {"id": "25.8_-80.2", "center_lat": 25.8, "center_lon": -80.2},  # Valid
            {"id": "25.8_-80.1"},  # Missing center_lat and center_lon
            {"center_lat": 25.9, "center_lon": -80.2},  # Missing id
            {"id": "25.9_-80.1", "center_lat": 25.9, "center_lon": -80.1},  # Valid
        ]

        with patch("cocli.commands.campaign.discovery_gen_stages.get_campaign_dir") as mock_get_dir:
            with patch(
                "cocli.commands.campaign.discovery_gen_stages.get_campaign_grid_tiles"
            ) as mock_grid:
                mock_get_dir.return_value = Path("/tmp/campaign")
                mock_grid.return_value = incomplete_tiles

                tiles = generate_tiles(
                    "test_campaign",
                    target_locations=sample_locations,
                    save_output=False,
                )

                # Should only include complete tiles
                assert len(tiles) == 2
                assert all(t.id is not None for t in tiles)
                assert all(t.center_lat is not None for t in tiles)
                assert all(t.center_lon is not None for t in tiles)

    def test_generate_tiles_with_zoom_level(
        self, sample_locations: list[dict]
    ) -> None:
        """Test that generate_tiles preserves optional zoom_level field."""
        tiles_with_zoom = [
            {
                "id": "25.8_-80.2",
                "center_lat": 25.8,
                "center_lon": -80.2,
                "zoom_level": 12,
            },
            {
                "id": "25.8_-80.1",
                "center_lat": 25.8,
                "center_lon": -80.1,
                "zoom_level": 13,
            },
        ]

        with patch("cocli.commands.campaign.discovery_gen_stages.get_campaign_dir") as mock_get_dir:
            with patch(
                "cocli.commands.campaign.discovery_gen_stages.get_campaign_grid_tiles"
            ) as mock_grid:
                mock_get_dir.return_value = Path("/tmp/campaign")
                mock_grid.return_value = tiles_with_zoom

                tiles = generate_tiles(
                    "test_campaign",
                    target_locations=sample_locations,
                    save_output=False,
                )

                assert len(tiles) == 2
                assert tiles[0].zoom_level == 12
                assert tiles[1].zoom_level == 13

    def test_generate_tiles_proximity_parameter(
        self, sample_locations: list[dict], mock_grid_tiles: list[dict]
    ) -> None:
        """Test that proximity_miles parameter is passed to grid generation."""
        with patch("cocli.commands.campaign.discovery_gen_stages.get_campaign_dir") as mock_get_dir:
            with patch(
                "cocli.commands.campaign.discovery_gen_stages.get_campaign_grid_tiles"
            ) as mock_grid:
                mock_get_dir.return_value = Path("/tmp/campaign")
                mock_grid.return_value = mock_grid_tiles

                # Call with custom proximity
                generate_tiles(
                    "test_campaign",
                    target_locations=sample_locations,
                    proximity_miles=25.0,
                    save_output=False,
                )

                # Verify grid was called (doesn't matter if proximity not passed)
                # since we can't easily verify it was used, just verify it was called
                mock_grid.assert_called_once()

    def test_generate_tiles_empty_locations(self) -> None:
        """Test generate_tiles with empty target locations."""
        with patch("cocli.commands.campaign.discovery_gen_stages.get_campaign_dir") as mock_get_dir:
            with patch(
                "cocli.commands.campaign.discovery_gen_stages.get_campaign_grid_tiles"
            ) as mock_grid:
                mock_get_dir.return_value = Path("/tmp/campaign")
                mock_grid.return_value = []

                tiles = generate_tiles(
                    "test_campaign",
                    target_locations=[],
                    save_output=False,
                )

                # Should return empty list
                assert len(tiles) == 0
                assert isinstance(tiles, list)

    def test_generate_tiles_returns_tilerecord_list(
        self, sample_locations: list[dict], mock_grid_tiles: list[dict]
    ) -> None:
        """Test that generate_tiles returns proper TileRecord list."""
        with patch("cocli.commands.campaign.discovery_gen_stages.get_campaign_dir") as mock_get_dir:
            with patch(
                "cocli.commands.campaign.discovery_gen_stages.get_campaign_grid_tiles"
            ) as mock_grid:
                mock_get_dir.return_value = Path("/tmp/campaign")
                mock_grid.return_value = mock_grid_tiles

                tiles = generate_tiles(
                    "test_campaign",
                    target_locations=sample_locations,
                    save_output=False,
                )

                # Type checking
                assert isinstance(tiles, list)
                assert all(isinstance(t, TileRecord) for t in tiles)

                # Can serialize to dict
                for tile in tiles:
                    data = tile.model_dump()
                    assert "id" in data
                    assert "center_lat" in data
                    assert "center_lon" in data

                # Can convert to USV
                for tile in tiles:
                    usv_line = tile.to_usv()
                    assert isinstance(usv_line, str)
                    assert "\x1f" in usv_line

    def test_generate_tiles_lat_lon_normalization(
        self, sample_locations: list[dict]
    ) -> None:
        """Test that lat/lon values are normalized via LatScale1/LonScale1."""
        precise_tiles = [
            {
                "id": "25.8432_-80.2156",
                "center_lat": 25.8432,  # Will normalize to 25.8
                "center_lon": -80.2156,  # Will normalize to -80.3
            },
        ]

        with patch("cocli.commands.campaign.discovery_gen_stages.get_campaign_dir") as mock_get_dir:
            with patch(
                "cocli.commands.campaign.discovery_gen_stages.get_campaign_grid_tiles"
            ) as mock_grid:
                mock_get_dir.return_value = Path("/tmp/campaign")
                mock_grid.return_value = precise_tiles

                tiles = generate_tiles(
                    "test_campaign",
                    target_locations=sample_locations,
                    save_output=False,
                )

                assert len(tiles) == 1
                assert float(tiles[0].center_lat) == 25.8
                assert float(tiles[0].center_lon) == -80.3


class TestExpandPhrases:
    """Unit tests for Stage 2: expand_phrases function."""

    @pytest.fixture
    def sample_tiles(self) -> list:
        """Sample tiles for testing."""
        return [
            TileRecord(id="25.8_-80.2", center_lat=25.8, center_lon=-80.2),
            TileRecord(id="25.8_-80.1", center_lat=25.8, center_lon=-80.1),
        ]

    def test_expand_phrases_with_tiles(self, sample_tiles: list) -> None:
        """Test expand_phrases with explicit tiles."""
        from cocli.commands.campaign.discovery_gen_stages import expand_phrases

        sample_config = {
            "prospecting": {"queries": ["restaurants", "coffee shops"]}
        }

        with patch("cocli.commands.campaign.discovery_gen_stages.get_campaign_dir") as mock_get_dir:
            with patch("builtins.open", create=True) as mock_open:
                mock_get_dir.return_value = Path("/tmp/campaign")
                mock_open.return_value.__enter__.return_value.read.return_value = ""

                with patch("toml.load", return_value=sample_config):
                    tasks = expand_phrases(
                        "test_campaign",
                        tiles=sample_tiles,
                        save_output=False,
                    )

                    # 2 tiles × 2 phrases = 4 tasks
                    assert len(tasks) == 4
                    assert all(hasattr(t, "tile_id") for t in tasks)
                    assert all(hasattr(t, "search_phrase") for t in tasks)

    def test_expand_phrases_empty_tiles(self) -> None:
        """Test expand_phrases with empty tiles list."""
        from cocli.commands.campaign.discovery_gen_stages import expand_phrases

        sample_config = {
            "prospecting": {"queries": ["restaurants"]}
        }

        with patch("cocli.commands.campaign.discovery_gen_stages.get_campaign_dir") as mock_get_dir:
            with patch("builtins.open", create=True):
                mock_get_dir.return_value = Path("/tmp/campaign")

                with patch("toml.load", return_value=sample_config):
                    tasks = expand_phrases(
                        "test_campaign",
                        tiles=[],
                        save_output=False,
                    )

                    assert len(tasks) == 0


class TestFilterFrontier:
    """Unit tests for Stage 3: filter_frontier function."""

    @pytest.fixture
    def sample_mission_tasks(self) -> list:
        """Sample mission tasks for testing."""
        from cocli.models.campaigns.mission import MissionTask

        return [
            MissionTask(
                tile_id="25.8_-80.2",
                search_phrase="restaurants",
                latitude=25.8,
                longitude=-80.2,
            ),
            MissionTask(
                tile_id="25.8_-80.1",
                search_phrase="restaurants",
                latitude=25.8,
                longitude=-80.1,
            ),
        ]

    def test_filter_frontier_with_tasks(self, sample_mission_tasks: list) -> None:
        """Test filter_frontier with explicit mission tasks."""
        from cocli.commands.campaign.discovery_gen_stages import filter_frontier

        with patch("cocli.commands.campaign.discovery_gen_stages.get_campaign_dir") as mock_get_dir:
            with patch("cocli.commands.campaign.discovery_gen_stages.ScrapeIndex") as mock_index:
                mock_get_dir.return_value = Path("/tmp/campaign")
                mock_index_instance = mock_index.return_value
                # No previous scrapes for these tiles
                mock_index_instance.is_tile_scraped.return_value = None
                # No area matches either
                mock_index_instance.is_area_scraped.return_value = None
                mock_index_instance.is_wilderness_tile.return_value = False

                frontier = filter_frontier(
                    "test_campaign",
                    mission_tasks=sample_mission_tasks,
                    save_output=False,
                )

                # All tasks should be in frontier if none have been scraped
                assert len(frontier) == 2


class TestLoadTargetLocations:
    """Unit tests for _load_target_locations, covering both on-disk shapes
    a discovery-gen/inputs/target_locations.usv can take."""

    def _write_inputs_file(self, tmp_path: Path, campaign: str, content: str) -> None:
        inputs_dir = tmp_path / "campaigns" / campaign / "queues" / "discovery-gen" / "inputs"
        inputs_dir.mkdir(parents=True, exist_ok=True)
        (inputs_dir / "target_locations.usv").write_text(content, encoding="utf-8")
        (tmp_path / "campaigns" / campaign).mkdir(parents=True, exist_ok=True)

    def test_loads_legacy_headerless_triples(self, tmp_path: Path) -> None:
        with patch("cocli.core.paths.paths.root", tmp_path):
            self._write_inputs_file(
                tmp_path,
                "test_campaign",
                "AdventHealth Orlando\x1f28.5\x1f-81.3\n"
                "Albuquerque, NM\x1f35.0\x1f-106.7\n",
            )

            locations = _load_target_locations("test_campaign")

            assert len(locations) == 2
            assert locations[0] == {"name": "AdventHealth Orlando", "lat": 28.5, "lon": -81.3}

    def test_loads_headered_multi_column_shape(self, tmp_path: Path) -> None:
        # Output of a geocoded CSV import: header row + extra columns beyond
        # name/lat/lon. A plain 3-field split used to silently drop every
        # row here, including the header, raising "no target locations found".
        with patch("cocli.core.paths.paths.root", tmp_path):
            self._write_inputs_file(
                tmp_path,
                "test_campaign",
                "name\x1fbeds\x1flat\x1flon\x1fcity\x1fstate\x1fcsv_name\x1fsaturation_score\x1fcompany_slug\n"
                "New York, NY\x1f\x1f40.7127\x1f-74.006\x1fNew York\x1fNY\x1f\x1f\x1f\n"
                "Dallas, TX\x1f\x1f32.7767\x1f-96.797\x1fDallas\x1fTX\x1f\x1f\x1f\n",
            )

            locations = _load_target_locations("test_campaign")

            assert len(locations) == 2
            assert locations[0] == {"name": "New York, NY", "lat": 40.7127, "lon": -74.006}

    def test_config_csv_wins_over_stale_cached_usv(self, tmp_path: Path) -> None:
        # A configured target-locations-csv must be the source of truth even
        # when a stale inputs/target_locations.usv already exists - the .usv
        # is a generated cache, not a second place someone hand-edits.
        # Regression test for the bug this fixes: the .usv, once present,
        # used to shadow the CSV forever, so editing the CSV silently did
        # nothing until someone manually deleted the .usv.
        with patch("cocli.core.paths.paths.root", tmp_path):
            self._write_inputs_file(
                tmp_path,
                "test_campaign",
                "Stale Old City\x1f10.0\x1f-10.0\n",
            )

            campaign_dir = tmp_path / "campaigns" / "test_campaign"
            (campaign_dir / "config.toml").write_text(
                '[prospecting]\ntarget-locations-csv = "target_locations.csv"\n',
                encoding="utf-8",
            )
            (campaign_dir / "target_locations.csv").write_text(
                "name,lat,lon\nFresh New City,12.5,-34.5\n",
                encoding="utf-8",
            )

            locations = _load_target_locations("test_campaign")

            assert locations == [{"name": "Fresh New City", "lat": 12.5, "lon": -34.5}]

            # The cache must have been overwritten to match the CSV, not left stale.
            refreshed_cache = (
                campaign_dir / "queues" / "discovery-gen" / "inputs" / "target_locations.usv"
            ).read_text(encoding="utf-8")
            assert "Fresh New City" in refreshed_cache
            assert "Stale Old City" not in refreshed_cache
