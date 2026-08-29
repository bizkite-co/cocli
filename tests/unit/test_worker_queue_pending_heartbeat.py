"""Unit tests for WorkerService._compute_queue_pending(): the piece that
lets a Pi node publish its own, correct pending-queue counts via the
heartbeat, instead of leaving the audit machine to read a local disk that
PiSyncService never syncs pending/ into. See task-agent ticket
scrape-pipeline-audit-tables-pending-counts-read-stale-local-dev-machine-queue-dirs-not-live-pi-state.
"""

from __future__ import annotations

import logging
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
async def test_compute_queue_pending_tops_up_gm_list_in_full_when_drained(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Once gm-list/pending/ is fully drained, the heartbeat check should
    copy the ENTIRE remaining discovery-gen/completed backlog in, not a
    small batch - pending/ is the real backlog signal (cocli audit
    scrape's stale-fallback path and its "Gm List Claimed" lease count
    both read it directly), and gm-list's own poll() early-terminates
    regardless of how many files sit there, so there's no per-poll cost
    to keeping the whole backlog resident. Mark, 2026-08-28: "we can dump
    them all in there at once ... it's just files."""
    with patch.object(paths, "root", tmp_path):
        campaign = "turboship"
        campaign_dir = tmp_path / "campaigns" / campaign

        # Three discovery-gen tiles, none scraped yet - real backlog.
        _write_dg_tile(campaign_dir, "1/40.0/-74.0", "phrase-one")
        _write_dg_tile(campaign_dir, "2/41.0/-75.0", "phrase-two")
        _write_dg_tile(campaign_dir, "3/42.0/-76.0", "phrase-three")
        (campaign_dir / "queues" / "gm-list" / "completed" / "results").mkdir(parents=True)

        # gm-list/pending/ starts empty (fully drained).
        supervisor = _make_supervisor(campaign)
        with caplog.at_level(logging.INFO, logger="cocli.application.worker_service"):
            result = await supervisor._compute_queue_pending()

        pending_dir = campaign_dir / "queues" / "gm-list" / "pending"
        copied_files = list(pending_dir.rglob("*.usv"))

    assert result["gm-list"] == 3  # candidates
    assert len(copied_files) == 3  # ALL candidates copied in, not a bounded batch
    assert "topped up 3 item(s)" in caplog.text  # real top-up IS logged


@pytest.mark.asyncio
async def test_compute_queue_pending_does_not_top_up_while_pending_still_has_work(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """As long as gm-list/pending/ still has at least one real item left,
    leave it alone - no copy, even if more discovery-gen candidates exist.
    Also asserts on the log line, not just the file count: EnqueueResult
    .copied counts candidates considered, not files actually written (its
    internal counter isn't gated on dry_run, only the real shutil.copy2
    call is) - it's nonzero even under dry_run=True, so a naive "if
    result.copied: log 'topped up'" falsely logs a top-up on every single
    heartbeat tick even when pending/ is well-stocked and no copy ran at
    all. Caught live: cocli5x1/roadmap logged "topped up 20399 item(s)"
    every ~40s for several minutes while the real file count stayed
    stable, 2026-08-28."""
    with patch.object(paths, "root", tmp_path):
        campaign = "turboship"
        campaign_dir = tmp_path / "campaigns" / campaign

        # One item already sitting in gm-list/pending/ - not yet drained.
        pending_item = campaign_dir / "queues" / "gm-list" / "pending" / "1" / "40.0" / "-74.0"
        pending_item.mkdir(parents=True)
        (pending_item / "existing-phrase.usv").write_text("dummy")

        # A real, unscraped discovery-gen candidate exists too, but should
        # NOT get copied in since pending/ still has work left.
        _write_dg_tile(campaign_dir, "2/41.0/-75.0", "phrase-two")
        (campaign_dir / "queues" / "gm-list" / "completed" / "results").mkdir(parents=True)

        supervisor = _make_supervisor(campaign)
        with caplog.at_level(logging.INFO, logger="cocli.application.worker_service"):
            result = await supervisor._compute_queue_pending()

        pending_dir = campaign_dir / "queues" / "gm-list" / "pending"
        copied_files = list(pending_dir.rglob("*.usv"))

    assert result["gm-list"] == 1  # candidates count still reported
    assert len(copied_files) == 1  # only the pre-existing file - no top-up copy happened
    assert "topped up" not in caplog.text  # no false "topped up" log on a dry-run tick


@pytest.mark.asyncio
async def test_tile_coverage_empty_campaign_returns_zeros(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        supervisor = _make_supervisor("brand-new-campaign")
        result = await supervisor._compute_gm_list_tile_coverage()

    assert result == {"staged_tiles": 0, "tiles_with_any_result": 0, "tiles_with_zero_results": 0}
