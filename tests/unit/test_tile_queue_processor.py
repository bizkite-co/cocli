"""process_tile_queue(): map-tile/pending/ -> discovery-gen/completed/.

map-tile has no processing phase (removed 2026-08-09) - this reads directly
from map-tile/pending/, explodes each tile's phrase rows into individual
ScrapeTask files under discovery-gen/completed/ (ScrapeTask's own
SOURCE_QUEUE/SOURCE_STATE, unchanged - this is discovery-gen's own correct,
permanent output, not something this fix touches), then moves the consumed
tile straight to map-tile/completed/.
"""

from pathlib import Path
from unittest.mock import patch

from cocli.core.paths import paths
from cocli.core.queue.factory import get_queue_manager
from cocli.models.campaigns.tile import TileRecord
from cocli.services.tile_queue_processor import process_tile_queue


def _write_tile_file(pending_dir: Path, rel_path: str, records: list[TileRecord]) -> Path:
    tile_path = pending_dir / rel_path
    tile_path.parent.mkdir(parents=True, exist_ok=True)
    with open(tile_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(r.to_usv())
    return tile_path


def test_process_tile_queue_reads_pending_not_processing(tmp_path):
    with patch("cocli.core.paths.paths.root", tmp_path):
        campaign_name = "test-campaign"
        tile_queue = get_queue_manager("map-tile", queue_type="tile", campaign_name=campaign_name)

        records = [
            TileRecord(tile_id="28.7_-96.9", search_phrase="rubber flooring contractor", latitude=28.7, longitude=-96.9),
            TileRecord(tile_id="28.7_-96.9", search_phrase="sports flooring contractor", latitude=28.7, longitude=-96.9),
        ]
        _write_tile_file(tile_queue.pending_dir, "2/28.7/-96.9/28.7_-96.9.usv", records)

        metrics = process_tile_queue(campaign_name)

        assert metrics["tiles_processed"] == 1
        assert metrics["scrape_tasks_created"] == 2
        assert metrics["errors"] == 0


def test_process_tile_queue_reports_identities_it_wrote(tmp_path):
    """metrics["identities"] is this call's own authoritative "what did I
    just write" list - a job run snapshots this directly (see
    job_run_service.py) rather than diffing discovery-gen/completed/
    before/after, since a before/after diff would also catch an older,
    still-unfinished run's leftover items if two runs' generation windows
    overlap in time. Identity format must match
    cocli/core/queue/reconcile.py's (shard-stripped, extension-stripped,
    "/"-joined) so it lines up with gm-list's own reconciliation."""
    with patch("cocli.core.paths.paths.root", tmp_path):
        campaign_name = "test-campaign"
        tile_queue = get_queue_manager("map-tile", queue_type="tile", campaign_name=campaign_name)

        records = [
            TileRecord(tile_id="28.7_-96.9", search_phrase="rubber flooring contractor", latitude=28.7, longitude=-96.9),
            TileRecord(tile_id="28.7_-96.9", search_phrase="sports flooring contractor", latitude=28.7, longitude=-96.9),
        ]
        _write_tile_file(tile_queue.pending_dir, "2/28.7/-96.9/28.7_-96.9.usv", records)

        metrics = process_tile_queue(campaign_name)

        assert sorted(metrics["identities"]) == [
            "28.7/-96.9/rubber-flooring-contractor",
            "28.7/-96.9/sports-flooring-contractor",
        ]


def test_process_tile_queue_explodes_into_discovery_gen_completed(tmp_path):
    with patch("cocli.core.paths.paths.root", tmp_path):
        campaign_name = "test-campaign"
        tile_queue = get_queue_manager("map-tile", queue_type="tile", campaign_name=campaign_name)

        records = [
            TileRecord(tile_id="28.7_-96.9", search_phrase="rubber flooring contractor", latitude=28.7, longitude=-96.9),
            TileRecord(tile_id="28.7_-96.9", search_phrase="sports flooring contractor", latitude=28.7, longitude=-96.9),
        ]
        _write_tile_file(tile_queue.pending_dir, "2/28.7/-96.9/28.7_-96.9.usv", records)

        process_tile_queue(campaign_name)

        discovery_gen_completed = paths.campaign(campaign_name).queue("discovery-gen").state("completed")
        created = sorted(p.name for p in discovery_gen_completed.rglob("*.usv"))
        assert created == ["rubber-flooring-contractor.usv", "sports-flooring-contractor.usv"]


def test_process_tile_queue_moves_tile_to_map_tile_completed_not_processing(tmp_path):
    with patch("cocli.core.paths.paths.root", tmp_path):
        campaign_name = "test-campaign"
        tile_queue = get_queue_manager("map-tile", queue_type="tile", campaign_name=campaign_name)

        records = [
            TileRecord(tile_id="28.7_-96.9", search_phrase="rubber flooring contractor", latitude=28.7, longitude=-96.9),
        ]
        tile_path = _write_tile_file(tile_queue.pending_dir, "2/28.7/-96.9/28.7_-96.9.usv", records)

        process_tile_queue(campaign_name)

        assert not tile_path.exists()
        assert (tile_queue.completed_dir / "2/28.7/-96.9/28.7_-96.9.usv").exists()
        assert not hasattr(tile_queue, "processing_dir")


def test_process_tile_queue_dry_run_writes_nothing(tmp_path):
    with patch("cocli.core.paths.paths.root", tmp_path):
        campaign_name = "test-campaign"
        tile_queue = get_queue_manager("map-tile", queue_type="tile", campaign_name=campaign_name)

        records = [
            TileRecord(tile_id="28.7_-96.9", search_phrase="rubber flooring contractor", latitude=28.7, longitude=-96.9),
        ]
        tile_path = _write_tile_file(tile_queue.pending_dir, "2/28.7/-96.9/28.7_-96.9.usv", records)

        metrics = process_tile_queue(campaign_name, dry_run=True)

        assert metrics["scrape_tasks_created"] == 0
        assert tile_path.exists()
        discovery_gen_completed = paths.campaign(campaign_name).queue("discovery-gen").state("completed")
        assert list(discovery_gen_completed.rglob("*.usv")) == []
