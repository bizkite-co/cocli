"""CLI-level tests for `cocli index clean-quote-corruption`."""

import re
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cocli.application.index_service import CleanQuoteCorruptionResult
from cocli.commands.index import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _clean(output: str) -> str:
    return _ANSI_RE.sub("", output)


def test_defaults_to_dry_run() -> None:
    fake_container = MagicMock()
    fake_container.index_service.clean_quote_corruption.return_value = CleanQuoteCorruptionResult(
        campaign_name="turboship", index_name="google_maps_prospects", dry_run=True,
        checkpoint_total=2, rows_cleaned=1, fields_affected={"name": 1},
        sample_place_ids=["ChIJDirty"],
    )

    with patch("cocli.commands.index.ServiceContainer", return_value=fake_container):
        result = runner.invoke(app, ["clean-quote-corruption", "--campaign", "turboship"])

    cleaned = _clean(result.output)
    assert result.exit_code == 0, cleaned
    assert "DRY RUN" in cleaned
    assert "ChIJDirty" in cleaned
    fake_container.index_service.clean_quote_corruption.assert_called_once_with(
        index_name="google_maps_prospects", dry_run=True
    )


def test_apply_flag_passes_dry_run_false() -> None:
    fake_container = MagicMock()
    fake_container.index_service.clean_quote_corruption.return_value = CleanQuoteCorruptionResult(
        campaign_name="turboship", index_name="google_maps_prospects", dry_run=False,
        checkpoint_total=1, rows_cleaned=0,
    )

    with patch("cocli.commands.index.ServiceContainer", return_value=fake_container):
        result = runner.invoke(app, ["clean-quote-corruption", "--campaign", "turboship", "--apply"])

    cleaned = _clean(result.output)
    assert result.exit_code == 0, cleaned
    assert "DRY RUN" not in cleaned
    fake_container.index_service.clean_quote_corruption.assert_called_once_with(
        index_name="google_maps_prospects", dry_run=False
    )
