"""CLI-level tests for `cocli index requeue-enrichment-gaps`."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cocli.application.index_service import RequeueResult, RequeueRow
from cocli.commands.index import app

runner = CliRunner()


def test_requeue_enrichment_gaps_exits_nonzero_on_ssh_error() -> None:
    fake_container = MagicMock()
    fake_container.index_service.requeue_enrichment_gaps.return_value = RequeueResult(
        campaign_name="test-campaign",
        index_name="enrichment",
        rows=[RequeueRow(place_id="PLACE_A", status="ssh_error", detail="permission denied")],
    )

    with patch("cocli.commands.index.ServiceContainer", return_value=fake_container):
        result = runner.invoke(
            app, ["requeue-enrichment-gaps", "PLACE_A", "--campaign", "test-campaign"]
        )

    assert result.exit_code == 1, result.output


def test_requeue_enrichment_gaps_skipped_is_not_a_failure() -> None:
    """"skipped" (already completed/pending/failed elsewhere) is a good,
    idempotent outcome - must not trip the exit code, unlike ssh_error."""
    fake_container = MagicMock()
    fake_container.index_service.requeue_enrichment_gaps.return_value = RequeueResult(
        campaign_name="test-campaign",
        index_name="enrichment",
        rows=[RequeueRow(place_id="PLACE_A", status="skipped", detail="already completed")],
    )

    with patch("cocli.commands.index.ServiceContainer", return_value=fake_container):
        result = runner.invoke(
            app, ["requeue-enrichment-gaps", "PLACE_A", "--campaign", "test-campaign"]
        )

    assert result.exit_code == 0, result.output


def test_requeue_enrichment_gaps_from_audit_csv_filters_by_gap_category(tmp_path: Path) -> None:
    csv_path = tmp_path / "audit.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["place_id", "gm_list", "gm_details", "pi_wal", "checkpoint",
             "enrichment", "verdict", "gap_category"]
        )
        writer.writerow(
            ["PLACE_GAP", "found", "completed", "present", "present",
             "never seen", "...", "Identity Gap (enrichment-enqueue)"]
        )
        writer.writerow(
            ["PLACE_CLEAN", "found", "completed", "present", "present",
             "completed", "...", "no gap"]
        )

    fake_container = MagicMock()
    fake_container.index_service.requeue_enrichment_gaps.return_value = RequeueResult(
        campaign_name="test-campaign", index_name="enrichment", rows=[]
    )

    with patch("cocli.commands.index.ServiceContainer", return_value=fake_container):
        result = runner.invoke(
            app,
            ["requeue-enrichment-gaps", "--from-audit-csv", str(csv_path),
             "--campaign", "test-campaign"],
        )

    assert result.exit_code == 0, result.output
    fake_container.index_service.requeue_enrichment_gaps.assert_called_once_with(["PLACE_GAP"])


def test_requeue_enrichment_gaps_errors_when_no_audit_csv_found(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """No place_id/--from-file/--from-audit-csv given, and no
    campaign_audit_*.csv exists yet to auto-select from - must exit
    nonzero with a clear message.

    Renamed and re-isolated 2026-09-17: the old name/assertion
    ("requires_exactly_one_source" / "exactly one" in the output)
    described a validation rule that no longer exists in
    cocli/commands/index.py - multiple campaign_audit_*.csv files are
    auto-selected by latest mtime, not rejected. The test had never
    actually exercised that current behavior; it passed only because it
    read paths.campaign("test-campaign").exports (module-global state,
    never monkeypatched here) and happened to find leftover files from
    OTHER test files sharing that same campaign name - a real
    cross-test-file isolation gap that silently broke once those
    leftovers stopped being present (e.g. after a /tmp cleanup)."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    result = runner.invoke(app, ["requeue-enrichment-gaps", "--campaign", "test-campaign"])
    assert result.exit_code == 1
    assert "no campaign_audit_*.csv found" in result.output.lower()
