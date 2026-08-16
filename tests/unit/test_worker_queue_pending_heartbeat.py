"""Unit tests for WorkerService._compute_queue_pending(): the piece that
lets a Pi node publish its own, correct pending-queue counts via the
heartbeat, instead of leaving the audit machine to read a local disk that
PiSyncService never syncs pending/ into. See task-agent ticket
scrape-pipeline-audit-tables-pending-counts-read-stale-local-dev-machine-queue-dirs-not-live-pi-state.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from cocli.application.worker_service import WorkerService
from cocli.core.paths import paths

US = "\x1f"


def _make_supervisor(campaign_name: str) -> WorkerService:
    supervisor = WorkerService.__new__(WorkerService)
    supervisor.campaign_name = campaign_name
    supervisor.processed_by = "test-node"
    return supervisor


@pytest.mark.asyncio
async def test_compute_queue_pending_counts_real_local_pending_files(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        campaign = "turboship"
        campaign_dir = tmp_path / "campaigns" / campaign

        # gm-details: two real pending tasks
        for place_id in ["PLACE_A", "PLACE_B"]:
            d = campaign_dir / "queues" / "gm-details" / "pending" / "x" / place_id
            d.mkdir(parents=True)
            (d / "task.json").write_text("{}")

        # enrichment: one real pending task
        d = campaign_dir / "queues" / "enrichment" / "pending" / "aa" / "example.com"
        d.mkdir(parents=True)
        (d / "task.json").write_text("{}")

        # gm-list: discovery-gen has one tile not yet in gm-list/completed
        (campaign_dir / "queues" / "discovery-gen" / "completed").mkdir(parents=True)
        (campaign_dir / "queues" / "discovery-gen" / "completed" / "tile1.usv").write_text(
            f"ChIJ1{US}Name\n"
        )
        (campaign_dir / "queues" / "gm-list" / "completed" / "results").mkdir(parents=True)

        supervisor = _make_supervisor(campaign)
        result = await supervisor._compute_queue_pending()

    assert result["gm-details"] == 2
    assert result["enrichment"] == 1
    assert result["gm-list"] == 1


@pytest.mark.asyncio
async def test_compute_queue_pending_empty_campaign_returns_zeros_not_error(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        supervisor = _make_supervisor("brand-new-campaign")
        result = await supervisor._compute_queue_pending()

    assert result.get("gm-details", 0) == 0
    assert result.get("enrichment", 0) == 0
    assert result.get("gm-list", 0) == 0


@pytest.mark.asyncio
async def test_push_supervisor_heartbeat_includes_queue_pending(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    with patch.object(paths, "root", tmp_path):
        campaign = "turboship"
        campaign_dir = tmp_path / "campaigns" / campaign
        d = campaign_dir / "queues" / "gm-details" / "pending" / "x" / "PLACE_A"
        d.mkdir(parents=True)
        (d / "task.json").write_text("{}")

        supervisor = WorkerService(campaign_name=campaign, processed_by="node1")
        supervisor.child_workers = []
        mock_s3 = MagicMock()

        with patch("psutil.cpu_percent", return_value=1.0), patch(
            "psutil.virtual_memory", return_value=MagicMock(percent=1.0)
        ):
            await supervisor._push_supervisor_heartbeat(mock_s3)

        import json

        body = json.loads(mock_s3.put_object.call_args.kwargs["Body"])
        assert body["queue_pending"]["gm-details"] == 1


def _write_dg_tile(campaign_dir: Path, tile: str, phrase: str) -> None:
    d = campaign_dir / "queues" / "discovery-gen" / "completed" / tile
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{phrase}.usv").write_text("dummy")


def _write_gm_list_receipt(campaign_dir: Path, tile: str, phrase: str, found_items: bool) -> None:
    d = campaign_dir / "queues" / "gm-list" / "completed" / "results" / tile
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{phrase}.json").write_text("{}")
    if found_items:
        (d / f"{phrase}.usv").write_text(f"PLACE_A{US}Name\n")


@pytest.mark.asyncio
async def test_tile_coverage_counts_receipts_not_usv_presence(tmp_path: Path) -> None:
    """A tile+phrase that legitimately found zero businesses still gets a
    completion receipt (.json) but no .usv file - counting .usv presence as
    the completion signal silently undercounts real coverage. Production
    bug confirmed 2026-08-16: cocli audit scrape reported 255 pending tiles
    via .usv-presence counting when the true, receipt-based figure was 2."""
    with patch.object(paths, "root", tmp_path):
        campaign = "turboship"
        campaign_dir = tmp_path / "campaigns" / campaign

        # Tile A: both phrases discovered, one found items, one found none -
        # both are real completions (receipts exist for both).
        _write_dg_tile(campaign_dir, "1/40.0/-74.0", "phrase-one")
        _write_dg_tile(campaign_dir, "1/40.0/-74.0", "phrase-two")
        _write_gm_list_receipt(campaign_dir, "1/40.0/-74.0", "phrase-one", found_items=True)
        _write_gm_list_receipt(campaign_dir, "1/40.0/-74.0", "phrase-two", found_items=False)

        # Tile B: discovered, never scraped at all.
        _write_dg_tile(campaign_dir, "2/41.0/-75.0", "phrase-one")

        supervisor = _make_supervisor(campaign)
        result = await supervisor._compute_gm_list_tile_coverage()

    assert result["staged_tiles"] == 2
    assert result["tiles_with_any_result"] == 1
    assert result["tiles_with_zero_results"] == 1


@pytest.mark.asyncio
async def test_tile_coverage_empty_campaign_returns_zeros(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        supervisor = _make_supervisor("brand-new-campaign")
        result = await supervisor._compute_gm_list_tile_coverage()

    assert result == {"staged_tiles": 0, "tiles_with_any_result": 0, "tiles_with_zero_results": 0}
