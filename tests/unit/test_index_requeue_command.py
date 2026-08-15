"""CLI-level tests for `cocli index requeue-stuck-details`."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cocli.application.index_service import RequeueResult, RequeueRow
from cocli.commands.index import app

runner = CliRunner()


def test_requeue_exits_zero_when_all_rows_requeued() -> None:
    fake_container = MagicMock()
    fake_container.index_service.requeue_stuck_details.return_value = RequeueResult(
        campaign_name="test-campaign",
        index_name="google_maps_prospects",
        rows=[RequeueRow(place_id="PLACE_A", status="requeued", detail="pushed to cocli5x0")],
    )

    with patch("cocli.commands.index.ServiceContainer", return_value=fake_container):
        result = runner.invoke(
            app, ["requeue-stuck-details", "PLACE_A", "--campaign", "test-campaign"]
        )

    assert result.exit_code == 0, result.output
    assert "PLACE_A" in result.output


def test_requeue_exits_nonzero_when_any_row_fails() -> None:
    fake_container = MagicMock()
    fake_container.index_service.requeue_stuck_details.return_value = RequeueResult(
        campaign_name="test-campaign",
        index_name="google_maps_prospects",
        rows=[RequeueRow(place_id="PLACE_A", status="ssh_error", detail="permission denied")],
    )

    with patch("cocli.commands.index.ServiceContainer", return_value=fake_container):
        result = runner.invoke(
            app, ["requeue-stuck-details", "PLACE_A", "--campaign", "test-campaign"]
        )

    assert result.exit_code == 1


def test_requeue_requires_place_id_or_from_file() -> None:
    result = runner.invoke(app, ["requeue-stuck-details", "--campaign", "test-campaign"])
    assert result.exit_code == 1


def test_requeue_rejects_both_place_id_and_from_file(tmp_path: Path) -> None:
    ids_file = tmp_path / "ids.txt"
    ids_file.write_text("PLACE_A\n")
    result = runner.invoke(
        app,
        [
            "requeue-stuck-details", "PLACE_A",
            "--from-file", str(ids_file), "--campaign", "test-campaign",
        ],
    )
    assert result.exit_code == 1


def test_requeue_batch_from_file() -> None:
    fake_container = MagicMock()
    fake_container.index_service.requeue_stuck_details.return_value = RequeueResult(
        campaign_name="test-campaign",
        index_name="google_maps_prospects",
        rows=[
            RequeueRow(place_id="PLACE_A", status="requeued", detail="pushed to cocli5x0"),
            RequeueRow(place_id="PLACE_B", status="not_found", detail="no gm-list result"),
        ],
    )

    with patch("cocli.commands.index.ServiceContainer", return_value=fake_container):
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("PLACE_A\nPLACE_B\n")
            ids_path = f.name

        result = runner.invoke(
            app,
            ["requeue-stuck-details", "--from-file", ids_path, "--campaign", "test-campaign"],
        )

    assert result.exit_code == 1  # PLACE_B was not_found
    assert "PLACE_A" in result.output
    assert "PLACE_B" in result.output
