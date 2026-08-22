"""CLI-level tests for `cocli index requeue-missing-details`."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cocli.application.index_service import RequeueResult, RequeueRow
from cocli.commands.index import app

runner = CliRunner()


def test_requeue_missing_details_exits_nonzero_on_ssh_error() -> None:
    fake_container = MagicMock()
    fake_container.index_service.requeue_missing_details.return_value = RequeueResult(
        campaign_name="test-campaign",
        index_name="google_maps_prospects",
        rows=[RequeueRow(place_id="PLACE_A", status="ssh_error", detail="permission denied")],
    )

    with patch("cocli.commands.index.ServiceContainer", return_value=fake_container):
        result = runner.invoke(
            app, ["requeue-missing-details", "PLACE_A", "--campaign", "test-campaign"]
        )

    assert result.exit_code == 1, result.output


def test_requeue_missing_details_skipped_is_not_a_failure() -> None:
    fake_container = MagicMock()
    fake_container.index_service.requeue_missing_details.return_value = RequeueResult(
        campaign_name="test-campaign",
        index_name="google_maps_prospects",
        rows=[RequeueRow(place_id="PLACE_A", status="skipped", detail="already completed")],
    )

    with patch("cocli.commands.index.ServiceContainer", return_value=fake_container):
        result = runner.invoke(
            app, ["requeue-missing-details", "PLACE_A", "--campaign", "test-campaign"]
        )

    assert result.exit_code == 0, result.output


def test_requeue_missing_details_requires_place_id_or_file() -> None:
    result = runner.invoke(app, ["requeue-missing-details", "--campaign", "test-campaign"])
    assert result.exit_code == 1


def test_requeue_missing_details_rejects_both_place_id_and_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    f = tmp_path / "ids.txt"
    f.write_text("PLACE_A\n")
    result = runner.invoke(
        app,
        ["requeue-missing-details", "PLACE_A", "--from-file", str(f), "--campaign", "test-campaign"],
    )
    assert result.exit_code == 1


def test_requeue_missing_details_from_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    f = tmp_path / "ids.txt"
    f.write_text("PLACE_A\nPLACE_B\n")

    fake_container = MagicMock()
    fake_container.index_service.requeue_missing_details.return_value = RequeueResult(
        campaign_name="test-campaign",
        index_name="google_maps_prospects",
        rows=[
            RequeueRow(place_id="PLACE_A", status="requeued", detail=""),
            RequeueRow(place_id="PLACE_B", status="requeued", detail=""),
        ],
    )

    with patch("cocli.commands.index.ServiceContainer", return_value=fake_container):
        result = runner.invoke(
            app,
            ["requeue-missing-details", "--from-file", str(f), "--campaign", "test-campaign"],
        )

    assert result.exit_code == 0, result.output
    fake_container.index_service.requeue_missing_details.assert_called_once_with(
        ["PLACE_A", "PLACE_B"], batch_size=1000
    )


def test_requeue_missing_details_batch_size_flag() -> None:
    fake_container = MagicMock()
    fake_container.index_service.requeue_missing_details.return_value = RequeueResult(
        campaign_name="test-campaign",
        index_name="google_maps_prospects",
        rows=[RequeueRow(place_id="PLACE_A", status="requeued", detail="")],
    )

    with patch("cocli.commands.index.ServiceContainer", return_value=fake_container):
        result = runner.invoke(
            app,
            ["requeue-missing-details", "PLACE_A", "--campaign", "test-campaign", "--batch-size", "50"],
        )

    assert result.exit_code == 0, result.output
    fake_container.index_service.requeue_missing_details.assert_called_once_with(
        ["PLACE_A"], batch_size=50
    )
