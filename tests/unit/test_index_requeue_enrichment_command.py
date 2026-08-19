"""CLI-level tests for `cocli index requeue-enrichment-gaps`."""

from __future__ import annotations

import csv
from pathlib import Path
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


def test_requeue_enrichment_gaps_requires_exactly_one_source() -> None:
    result = runner.invoke(app, ["requeue-enrichment-gaps", "--campaign", "test-campaign"])
    assert result.exit_code == 1
    assert "exactly one" in result.output.lower()
