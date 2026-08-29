"""CLI-level test for `cocli dev process-map-tile`'s ScrapeJobRun wiring:
generation auto-creates a run and immediately enqueues its identities into
gm-list/pending/ as the run's own last step - the only thing that can ever
cause new work to land there (see cocli/models/campaigns/scrape_job_run.py).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from cocli.application import job_run_service as jrs
from cocli.commands.dev import app
from cocli.core.paths import paths
from cocli.core.queue.factory import get_queue_manager
from cocli.models.campaigns.queues.gm_list import ScrapeTask
from cocli.models.campaigns.tile import TileRecord

runner = CliRunner()


def _write_tile_file(pending_dir: Path, rel_path: str, records: list[TileRecord]) -> None:
    tile_path = pending_dir / rel_path
    tile_path.parent.mkdir(parents=True, exist_ok=True)
    with open(tile_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(r.to_usv())


def test_process_map_tile_creates_run_and_enqueues_gm_list(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        campaign_name = "test-campaign"
        campaign_dir = tmp_path / "campaigns" / campaign_name
        campaign_dir.mkdir(parents=True)

        tile_queue = get_queue_manager("map-tile", queue_type="tile", campaign_name=campaign_name)
        records = [
            TileRecord(
                tile_id="28.7_-96.9",
                search_phrase="rubber flooring contractor",
                latitude=28.7,
                longitude=-96.9,
            ),
        ]
        _write_tile_file(tile_queue.pending_dir, "2/28.7/-96.9/28.7_-96.9.usv", records)

        result = runner.invoke(app, ["process-map-tile", campaign_name])

        assert result.exit_code == 0, result.output
        assert "Job run" in result.output

        runs = jrs._load_index(campaign_name)
        assert len(runs) == 1
        run = runs[0]
        assert run.identity_count == 1
        assert run.discovery_gen_completed_at is not None
        assert run.started_at is not None

        gm_list_q = get_queue_manager("gm-list", queue_type="gm-list", campaign_name=campaign_name)
        copied = list(gm_list_q.pending_dir.rglob("*.usv"))
        assert len(copied) == 1
        assert copied[0].name == "rubber-flooring-contractor.usv"

        copied_task = ScrapeTask.from_usv(copied[0].read_text(encoding="utf-8"))
        assert copied_task.job_run_id == run.id


def test_process_map_tile_dry_run_creates_no_job_run(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        campaign_name = "test-campaign"
        campaign_dir = tmp_path / "campaigns" / campaign_name
        campaign_dir.mkdir(parents=True)

        tile_queue = get_queue_manager("map-tile", queue_type="tile", campaign_name=campaign_name)
        records = [
            TileRecord(
                tile_id="28.7_-96.9",
                search_phrase="rubber flooring contractor",
                latitude=28.7,
                longitude=-96.9,
            ),
        ]
        _write_tile_file(tile_queue.pending_dir, "2/28.7/-96.9/28.7_-96.9.usv", records)

        result = runner.invoke(app, ["process-map-tile", campaign_name, "--dry-run"])

        assert result.exit_code == 0, result.output
        assert "Job run" not in result.output
        assert jrs._load_index(campaign_name) == []
