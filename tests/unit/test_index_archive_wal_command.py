"""CLI-level tests for `cocli index archive-incomplete-wal`."""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cocli.application.index_service import ArchiveWalNodeResult, ArchiveWalResult
from cocli.commands.index import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _clean_output(output: str) -> str:
    """Strip ANSI codes and collapse whitespace/newlines so a Rich-wrapped
    title (e.g. table titles wrapping "DRY RUN" across lines) can still be
    matched as a plain substring."""
    return " ".join(_ANSI_RE.sub("", output).split())


def test_defaults_to_dry_run() -> None:
    fake_container = MagicMock()
    fake_container.index_service.archive_incomplete_schema_wal.return_value = ArchiveWalResult(
        campaign_name="roadmap", index_name="google_maps_prospects",
        required_field_count=57, dry_run=True,
        nodes=[ArchiveWalNodeResult(hostname="cocli5x1", archived=24227, kept=7594)],
    )

    with patch("cocli.commands.index.ServiceContainer", return_value=fake_container):
        result = runner.invoke(app, ["archive-incomplete-wal", "--campaign", "roadmap"])

    assert result.exit_code == 0, result.output
    assert "DRY RUN" in _clean_output(result.output)
    assert "24227" in result.output
    fake_container.index_service.archive_incomplete_schema_wal.assert_called_once_with(
        index_name="google_maps_prospects", required_field_count=57, dry_run=True
    )


def test_apply_flag_passes_dry_run_false() -> None:
    fake_container = MagicMock()
    fake_container.index_service.archive_incomplete_schema_wal.return_value = ArchiveWalResult(
        campaign_name="roadmap", index_name="google_maps_prospects",
        required_field_count=57, dry_run=False,
        nodes=[ArchiveWalNodeResult(hostname="cocli5x1", archived=24227, kept=7594)],
    )

    with patch("cocli.commands.index.ServiceContainer", return_value=fake_container):
        result = runner.invoke(app, ["archive-incomplete-wal", "--campaign", "roadmap", "--apply"])

    assert result.exit_code == 0, result.output
    assert "APPLIED" in _clean_output(result.output)
    fake_container.index_service.archive_incomplete_schema_wal.assert_called_once_with(
        index_name="google_maps_prospects", required_field_count=57, dry_run=False
    )


def test_exits_nonzero_on_node_error() -> None:
    fake_container = MagicMock()
    fake_container.index_service.archive_incomplete_schema_wal.return_value = ArchiveWalResult(
        campaign_name="roadmap", index_name="google_maps_prospects",
        required_field_count=57, dry_run=True,
        nodes=[ArchiveWalNodeResult(hostname="cocli5x1", error="timeout")],
    )

    with patch("cocli.commands.index.ServiceContainer", return_value=fake_container):
        result = runner.invoke(app, ["archive-incomplete-wal", "--campaign", "roadmap"])

    assert result.exit_code == 1
