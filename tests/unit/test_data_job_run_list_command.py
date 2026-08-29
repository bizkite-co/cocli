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


def test_job_run_requeue_creates_new_run(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        campaign = "turboship"
        campaign_dir = tmp_path / "campaigns" / campaign
        dg_file = (
            campaign_dir / "queues" / "discovery-gen" / "completed" / "2" / "28.7" / "-96.9" / "item-a.usv"
        )
        dg_file.parent.mkdir(parents=True, exist_ok=True)
        dg_file.write_text("dummy\x1fscrape-task\n")

        previous = jrs.create_job_run(campaign, hostname="dev-machine")
        previous = jrs.mark_discovery_gen_completed(previous, ["28.7/-96.9/item-a"])

        result = runner.invoke(
            app, ["job-run", "requeue", previous.id, "--campaign", campaign]
        )

        assert result.exit_code == 0, result.output
        assert "Job run" in result.output
        runs = jrs._load_index(campaign)
        assert len(runs) == 2


def test_job_run_requeue_unknown_run_exits_nonzero(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        result = runner.invoke(
            app, ["job-run", "requeue", "no-such-run", "--campaign", "turboship"]
        )

    assert result.exit_code == 1
    assert "no-such-run" in result.output


def test_job_run_requeue_latest_picks_most_recent_run(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        campaign = "turboship"
        campaign_dir = tmp_path / "campaigns" / campaign
        for slug in ("item-a", "item-b"):
            dg_file = (
                campaign_dir
                / "queues"
                / "discovery-gen"
                / "completed"
                / "2"
                / "28.7"
                / "-96.9"
                / f"{slug}.usv"
            )
            dg_file.parent.mkdir(parents=True, exist_ok=True)
            dg_file.write_text("dummy\x1fscrape-task\n")

        older = jrs.create_job_run(campaign, hostname="node-a")
        older = jrs.mark_discovery_gen_completed(older, ["28.7/-96.9/item-a"])
        newer = jrs.create_job_run(campaign, hostname="node-b")
        newer = jrs.mark_discovery_gen_completed(newer, ["28.7/-96.9/item-b"])

        result = runner.invoke(
            app, ["job-run", "requeue", "--latest", "--campaign", campaign]
        )

        assert result.exit_code == 0, result.output
        assert f"from {newer.id}" in result.output
        assert older.id not in result.output


def test_job_run_requeue_latest_with_no_runs_exits_nonzero(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        result = runner.invoke(
            app, ["job-run", "requeue", "--latest", "--campaign", "brand-new"]
        )

    assert result.exit_code == 1
    assert "No job runs found" in result.output


def test_job_run_requeue_rejects_both_run_id_and_latest(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        result = runner.invoke(
            app,
            ["job-run", "requeue", "some-run-id", "--latest", "--campaign", "turboship"],
        )

    assert result.exit_code == 1
    assert "exactly one" in result.output


def test_job_run_requeue_rejects_neither_run_id_nor_latest(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        result = runner.invoke(app, ["job-run", "requeue", "--campaign", "turboship"])

    assert result.exit_code == 1
    assert "exactly one" in result.output
