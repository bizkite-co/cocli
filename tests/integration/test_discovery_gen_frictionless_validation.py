"""
Integration tests for discovery-gen pipeline Frictionless Data validation.

Tests that pipeline outputs conform to their Frictionless Data schemas
and that schema_hash versioning works correctly.
"""

import json
import tempfile
from pathlib import Path


from cocli.models.campaigns.tiles import TileRecord
from cocli.models.campaigns.mission import MissionTask
from cocli.core.geo_types import LatScale1, LonScale1
from cocli.core.frictionless_validation import (
    validate_usv_file,
    validate_schema_hash,
)


class TestTileRecordFrictionlessValidation:
    """Test Frictionless Data validation for TileRecord outputs."""

    def test_tiles_usv_round_trip_with_schema(self) -> None:
        """Test that tiles.usv and its schema are valid."""
        tiles = [
            TileRecord(
                id="25.8_-80.2",
                center_lat=LatScale1(25.8),
                center_lon=LonScale1(-80.2),
            ),
            TileRecord(
                id="25.8_-80.1",
                center_lat=LatScale1(25.8),
                center_lon=LonScale1(-80.1),
                zoom_level=12,
            ),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            tiles_dir = tmppath / "tiles"
            tiles_dir.mkdir()

            # Save tiles with datapackage.json
            tiles_path = tiles_dir / "tiles.usv"
            TileRecord.save_usv_with_datapackage(tiles, tiles_path, "tiles")

            # Verify files exist
            assert tiles_path.exists()
            schema_path = tiles_dir / "datapackage.json"
            assert schema_path.exists()

            # Validate USV file against schema
            is_valid, count, errors = validate_usv_file(tiles_path, schema_path)
            assert is_valid, f"Validation failed: {errors}"
            assert count == 2

    def test_tiles_schema_hash_present(self) -> None:
        """Test that tiles schema includes cocli:schema_hash."""
        tiles = [
            TileRecord(
                id="25.8_-80.2",
                center_lat=LatScale1(25.8),
                center_lon=LonScale1(-80.2),
            ),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            tiles_dir = tmppath / "tiles"
            tiles_dir.mkdir()

            tiles_path = tiles_dir / "tiles.usv"
            TileRecord.save_usv_with_datapackage(tiles, tiles_path, "tiles")

            schema_path = tiles_dir / "datapackage.json"
            with open(schema_path, "r") as f:
                schema = json.load(f)

            # Check for cocli metadata (stored as top-level keys with cocli: prefix)
            assert "cocli:schema_hash" in schema
            # Canonical form: {resource_name: hash}
            schema_hash = schema["cocli:schema_hash"]["tiles"]
            # Hash is a hex string generated from schema fields
            assert len(schema_hash) == 16  # Typically 16 hex chars


class TestMissionTaskFrictionlessValidation:
    """Test Frictionless Data validation for MissionTask outputs."""

    def test_mission_usv_round_trip_with_schema(self) -> None:
        """Test that mission.usv and its schema are valid."""
        tasks = [
            MissionTask(
                tile_id="25.8_-80.2",
                search_phrase="restaurants",
                latitude=LatScale1(25.8),
                longitude=LonScale1(-80.2),
            ),
            MissionTask(
                tile_id="25.8_-80.1",
                search_phrase="coffee",
                latitude=LatScale1(25.8),
                longitude=LonScale1(-80.1),
            ),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Save mission with datapackage.json
            mission_path = tmppath / "mission.usv"
            MissionTask.save_usv_with_datapackage(tasks, mission_path, "mission")

            schema_path = tmppath / "datapackage.json"
            assert schema_path.exists()

            # Validate USV file against schema
            is_valid, count, errors = validate_usv_file(mission_path, schema_path)
            assert is_valid, f"Validation failed: {errors}"
            assert count == 2

    def test_frontier_usv_with_schema(self) -> None:
        """Test that frontier.usv (MissionTask subset) validates correctly."""
        frontier = [
            MissionTask(
                tile_id="25.8_-80.2",
                search_phrase="restaurants",
                latitude=LatScale1(25.8),
                longitude=LonScale1(-80.2),
            ),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            pending_dir = tmppath / "pending"
            pending_dir.mkdir()

            # Save frontier with datapackage.json
            frontier_path = pending_dir / "frontier.usv"
            MissionTask.save_usv_with_datapackage(
                frontier, frontier_path, "frontier"
            )

            schema_path = pending_dir / "datapackage.json"
            assert schema_path.exists()

            # Validate USV file against schema
            is_valid, count, errors = validate_usv_file(frontier_path, schema_path)
            assert is_valid, f"Validation failed: {errors}"
            assert count == 1


class TestSchemaDeterminism:
    """Test that schema generation is deterministic."""

    def test_tiles_schema_hash_deterministic(self) -> None:
        """Test that TileRecord produces deterministic schema hashes."""
        tiles = [
            TileRecord(
                id="25.8_-80.2",
                center_lat=LatScale1(25.8),
                center_lon=LonScale1(-80.2),
            ),
        ]

        hashes = []
        for i in range(3):
            with tempfile.TemporaryDirectory() as tmpdir:
                tmppath = Path(tmpdir)
                tiles_dir = tmppath / "tiles"
                tiles_dir.mkdir()

                tiles_path = tiles_dir / "tiles.usv"
                TileRecord.save_usv_with_datapackage(tiles, tiles_path, "tiles")

                schema_path = tiles_dir / "datapackage.json"
                with open(schema_path, "r") as f:
                    schema = json.load(f)
                    hash_value = schema["cocli:schema_hash"]
                    hashes.append(hash_value)

        # All hashes should be identical
        assert hashes[0] == hashes[1]
        assert hashes[1] == hashes[2]

    def test_mission_schema_hash_deterministic(self) -> None:
        """Test that MissionTask produces deterministic schema hashes."""
        tasks = [
            MissionTask(
                tile_id="25.8_-80.2",
                search_phrase="restaurants",
                latitude=LatScale1(25.8),
                longitude=LonScale1(-80.2),
            ),
        ]

        hashes = []
        for i in range(3):
            with tempfile.TemporaryDirectory() as tmpdir:
                tmppath = Path(tmpdir)
                mission_path = tmppath / "mission.usv"
                MissionTask.save_usv_with_datapackage(tasks, mission_path, "mission")

                schema_path = tmppath / "datapackage.json"
                with open(schema_path, "r") as f:
                    schema = json.load(f)
                    hash_value = schema["cocli:schema_hash"]
                    hashes.append(hash_value)

        # All hashes should be identical
        assert hashes[0] == hashes[1]
        assert hashes[1] == hashes[2]


class TestSchemaHashValidation:
    """Test schema hash validation utility."""

    def test_validate_schema_hash_matches(self) -> None:
        """Test validation when hash matches."""
        tiles = [
            TileRecord(
                id="25.8_-80.2",
                center_lat=LatScale1(25.8),
                center_lon=LonScale1(-80.2),
            ),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            tiles_dir = tmppath / "tiles"
            tiles_dir.mkdir()

            tiles_path = tiles_dir / "tiles.usv"
            TileRecord.save_usv_with_datapackage(tiles, tiles_path, "tiles")

            schema_path = tiles_dir / "datapackage.json"

            # Get actual hash
            with open(schema_path, "r") as f:
                schema = json.load(f)
                expected_hash = schema["cocli:schema_hash"]["tiles"]

            # Validate with expected hash
            is_valid, actual_hash = validate_schema_hash(schema_path, expected_hash)
            assert is_valid
            assert actual_hash == expected_hash

    def test_validate_schema_hash_mismatch(self) -> None:
        """Test validation when hash doesn't match."""
        tiles = [
            TileRecord(
                id="25.8_-80.2",
                center_lat=LatScale1(25.8),
                center_lon=LonScale1(-80.2),
            ),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            tiles_dir = tmppath / "tiles"
            tiles_dir.mkdir()

            tiles_path = tiles_dir / "tiles.usv"
            TileRecord.save_usv_with_datapackage(tiles, tiles_path, "tiles")

            schema_path = tiles_dir / "datapackage.json"

            # Validate with wrong hash
            is_valid, actual_hash = validate_schema_hash(
                schema_path, "sha256:wrong_hash"
            )
            assert not is_valid
            assert actual_hash != "sha256:wrong_hash"


class TestUSVFieldCount:
    """Test that USV serialization preserves field count."""

    def test_tile_record_field_count(self) -> None:
        """Test TileRecord USV field count with/without zoom_level."""
        # Without zoom_level
        tile1 = TileRecord(
            id="25.8_-80.2",
            center_lat=LatScale1(25.8),
            center_lon=LonScale1(-80.2),
        )
        usv1 = tile1.to_usv()
        fields1 = usv1.strip().split("\x1f")
        assert len(fields1) == 3  # id, lat, lon

        # With zoom_level
        tile2 = TileRecord(
            id="25.8_-80.2",
            center_lat=LatScale1(25.8),
            center_lon=LonScale1(-80.2),
            zoom_level=12,
        )
        usv2 = tile2.to_usv()
        fields2 = usv2.strip().split("\x1f")
        assert len(fields2) == 4  # id, lat, lon, zoom_level

    def test_mission_task_field_count(self) -> None:
        """Test MissionTask USV field count is consistent."""
        task = MissionTask(
            tile_id="25.8_-80.2",
            search_phrase="restaurants",
            latitude=LatScale1(25.8),
            longitude=LonScale1(-80.2),
        )
        usv = task.to_usv()
        fields = usv.strip().split("\x1f")
        assert len(fields) == 4  # tile_id, phrase, lat, lon
