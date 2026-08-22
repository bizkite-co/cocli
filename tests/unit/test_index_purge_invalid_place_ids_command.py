"""CLI-level tests for `cocli index purge-invalid-place-ids`."""

import re
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cocli.application.index_service import PurgeInvalidPlaceIdsResult
from cocli.commands.index import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _clean(output: str) -> str:
    return _ANSI_RE.sub("", output)


def test_defaults_to_dry_run() -> None:
    fake_container = MagicMock()
    fake_container.index_service.purge_invalid_place_ids.return_value = PurgeInvalidPlaceIdsResult(
        campaign_name="turboship", index_name="google_maps_prospects", dry_run=True,
        removed_place_ids=["0xabc:0xdef"], checkpoint_before=2, checkpoint_after=1,
    )

    with patch("cocli.commands.index.ServiceContainer", return_value=fake_container):
        result = runner.invoke(app, ["purge-invalid-place-ids", "--campaign", "turboship"])

    cleaned = _clean(result.output)
    assert result.exit_code == 0, cleaned
    assert "DRY RUN" in cleaned
    assert "0xabc:0xdef" in cleaned
    fake_container.index_service.purge_invalid_place_ids.assert_called_once_with(
        index_name="google_maps_prospects", dry_run=True
    )


def test_apply_flag_passes_dry_run_false() -> None:
    fake_container = MagicMock()
    fake_container.index_service.purge_invalid_place_ids.return_value = PurgeInvalidPlaceIdsResult(
        campaign_name="turboship", index_name="google_maps_prospects", dry_run=False,
        removed_place_ids=[], checkpoint_before=1, checkpoint_after=1,
    )

    with patch("cocli.commands.index.ServiceContainer", return_value=fake_container):
        result = runner.invoke(app, ["purge-invalid-place-ids", "--campaign", "turboship", "--apply"])

    cleaned = _clean(result.output)
    assert result.exit_code == 0, cleaned
    assert "DRY RUN" not in cleaned
    fake_container.index_service.purge_invalid_place_ids.assert_called_once_with(
        index_name="google_maps_prospects", dry_run=False
    )
