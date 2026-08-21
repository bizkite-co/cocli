"""CLI-level tests for `cocli data compact-emails`."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cocli.commands.data import app

runner = CliRunner()


def test_compact_emails_success() -> None:
    fake_container = MagicMock()
    fake_container.data_sync_service.compact_index.return_value = {
        "status": "success",
        "message": "Email index compacted (Hot Inbox -> Shards)",
    }

    with patch("cocli.commands.data.ServiceContainer", return_value=fake_container) as mock_sc:
        result = runner.invoke(app, ["compact-emails", "--campaign", "roadmap"])

    assert result.exit_code == 0, result.output
    assert "compacted" in result.output
    mock_sc.assert_called_once_with(campaign_name="roadmap")
    fake_container.data_sync_service.compact_index.assert_called_once_with()


def test_compact_emails_error_exits_nonzero() -> None:
    fake_container = MagicMock()
    fake_container.data_sync_service.compact_index.return_value = {
        "status": "error",
        "message": "boom",
    }

    with patch("cocli.commands.data.ServiceContainer", return_value=fake_container):
        result = runner.invoke(app, ["compact-emails", "--campaign", "roadmap"])

    assert result.exit_code == 1
    assert "boom" in result.output
