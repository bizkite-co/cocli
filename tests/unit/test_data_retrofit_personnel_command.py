"""CLI-level tests for `cocli data retrofit-personnel-names`."""

import re
from unittest.mock import patch

from typer.testing import CliRunner

from cocli.application.email_personnel_retrofit import RetrofitResult
from cocli.commands.data import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _clean(output: str) -> str:
    return _ANSI_RE.sub("", output)


def test_defaults_to_dry_run() -> None:
    fake_result = RetrofitResult(
        campaign_name="roadmap", dry_run=True, scanned=10, matched=3, sample_names=["Keeley Watkins"]
    )
    with patch(
        "cocli.application.email_personnel_retrofit.retrofit_personnel_names",
        return_value=fake_result,
    ) as mock_retrofit:
        result = runner.invoke(app, ["retrofit-personnel-names", "--campaign", "roadmap"])

    cleaned = _clean(result.output)
    assert result.exit_code == 0, cleaned
    assert "DRY RUN" in cleaned
    assert "Scanned: 10" in cleaned
    assert "Matched: 3" in cleaned
    assert "Keeley Watkins" in cleaned
    mock_retrofit.assert_called_once_with("roadmap", dry_run=True)


def test_apply_flag_passes_dry_run_false() -> None:
    fake_result = RetrofitResult(campaign_name="roadmap", dry_run=False, scanned=10, matched=3)
    with patch(
        "cocli.application.email_personnel_retrofit.retrofit_personnel_names",
        return_value=fake_result,
    ) as mock_retrofit:
        result = runner.invoke(app, ["retrofit-personnel-names", "--campaign", "roadmap", "--apply"])

    cleaned = _clean(result.output)
    assert result.exit_code == 0, cleaned
    assert "DRY RUN" not in cleaned
    mock_retrofit.assert_called_once_with("roadmap", dry_run=False)
