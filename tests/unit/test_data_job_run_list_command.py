"""CLI-level smoke test for `cocli data job-run list`."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from cocli.application import job_run_service as jrs
from cocli.commands.data import app
from cocli.core.paths import paths

runner = CliRunner()


def test_job_run_list_shows_runs_newest_first(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        campaign = "turboship"
        first = jrs.create_job_run(campaign, hostname="node-a")
        second = jrs.create_job_run(campaign, hostname="node-b")
        second = jrs.mark_discovery_gen_completed(second, ["28.7/-96.9/x"])

        # Wide terminal - Rich's default 80-column table wrap truncates the
        # long run IDs before they'd be checkable below.
        result = runner.invoke(
            app, ["job-run", "list", "--campaign", campaign], env={"COLUMNS": "220"}
        )

    assert result.exit_code == 0, result.output
    assert first.id in result.output
    assert second.id in result.output
    # Newest first: second's id should appear before first's in the output.
    assert result.output.index(second.id) < result.output.index(first.id)


def test_job_run_list_empty_campaign(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        result = runner.invoke(app, ["job-run", "list", "--campaign", "brand-new"])

    assert result.exit_code == 0, result.output
    assert "Job Runs: brand-new" in result.output
