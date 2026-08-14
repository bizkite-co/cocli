"""CLI-level tests for `cocli index trace`'s output-path defaulting.

Batch mode must write into the campaign's own exports/ directory by
default, not wherever the shell's CWD happens to be - trace reports are
campaign data (a 2026-08-14 review caught two such files sitting at the
repo root instead, left over from the ad hoc script this command
replaced).
"""

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cocli.application.index_service import ProspectTraceResult, ProspectTraceRow
from cocli.commands.index import app
from cocli.core.paths import paths

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _clean_output(output: str) -> str:
    """Strip ANSI color codes and newlines so a Rich-wrapped/colored phrase
    can still be matched as a plain contiguous substring."""
    return _ANSI_RE.sub("", output).replace("\n", "")


def _fake_result(n: int) -> ProspectTraceResult:
    return ProspectTraceResult(
        campaign_name="test-campaign",
        index_name="google_maps_prospects",
        rows=[
            ProspectTraceRow(
                place_id=f"PLACE_{i}",
                gm_list="found",
                gm_details="completed",
                pi_wal="absent",
                checkpoint="present",
                verdict="present in current checkpoint",
            )
            for i in range(n)
        ],
    )


def test_trace_batch_defaults_output_to_campaign_exports_dir(tmp_path: Path) -> None:
    paths.root = tmp_path
    ids_file = tmp_path / "ids.txt"
    ids_file.write_text("PLACE_0\nPLACE_1\n")

    fake_container = MagicMock()
    fake_container.index_service.trace_prospects.return_value = _fake_result(2)

    with patch("cocli.commands.index.ServiceContainer", return_value=fake_container):
        result = runner.invoke(
            app,
            ["trace", "--from-file", str(ids_file), "--campaign", "test-campaign"],
        )

    assert result.exit_code == 0, result.output
    expected_dir = tmp_path / "campaigns" / "test-campaign" / "exports"
    written = list(expected_dir.glob("prospect_trace_google_maps_prospects_*.csv"))
    assert len(written) == 1, (
        f"expected one file in {expected_dir}, found "
        f"{list(expected_dir.iterdir()) if expected_dir.exists() else 'nothing'}"
    )
    # Rich wraps long paths and inserts color codes mid-phrase at the
    # CliRunner's terminal width - clean before matching so that doesn't
    # produce a false failure.
    cleaned_output = _clean_output(result.output)
    assert "Wrote 2 rows to" in cleaned_output
    assert written[0].name in cleaned_output


def test_trace_batch_respects_explicit_out_path(tmp_path: Path) -> None:
    paths.root = tmp_path
    ids_file = tmp_path / "ids.txt"
    ids_file.write_text("PLACE_0\nPLACE_1\n")
    custom_out = tmp_path / "scratch" / "custom.csv"

    fake_container = MagicMock()
    fake_container.index_service.trace_prospects.return_value = _fake_result(2)

    with patch("cocli.commands.index.ServiceContainer", return_value=fake_container):
        result = runner.invoke(
            app,
            [
                "trace", "--from-file", str(ids_file), "--campaign", "test-campaign",
                "--out", str(custom_out),
            ],
        )

    assert result.exit_code == 0, result.output
    assert custom_out.exists()
    # An explicit path is honored as-is - it must not also land in exports/.
    assert not (tmp_path / "campaigns" / "test-campaign" / "exports").exists()


def test_trace_single_item_does_not_write_a_file(tmp_path: Path) -> None:
    paths.root = tmp_path
    fake_container = MagicMock()
    fake_container.index_service.trace_prospects.return_value = _fake_result(1)

    with patch("cocli.commands.index.ServiceContainer", return_value=fake_container):
        result = runner.invoke(app, ["trace", "PLACE_0", "--campaign", "test-campaign"])

    assert result.exit_code == 0, result.output
    exports_dir = tmp_path / "campaigns" / "test-campaign" / "exports"
    assert not exports_dir.exists() or not list(exports_dir.glob("*.csv"))
