from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from cocli.commands.smart_sync import app

runner = CliRunner()


def test_smart_sync_all_single_campaign() -> None:
    with patch("cocli.commands.smart_sync.sync_campaign_config") as mock_cfg, patch(
        "cocli.commands.smart_sync.sync_prospects"
    ) as mock_pros, patch(
        "cocli.commands.smart_sync.sync_emails"
    ) as mock_emails, patch(
        "cocli.commands.smart_sync.sync_queues"
    ) as mock_queues:
        result = runner.invoke(app, ["all", "-c", "roadmap"])
        assert result.exit_code == 0
        mock_cfg.assert_called_once_with("roadmap")
        mock_pros.assert_called_once_with("roadmap", 20, False, False)
        mock_emails.assert_called_once_with("roadmap", 20, False, False)
        mock_queues.assert_called_once_with("roadmap", 20, False, False)


def test_smart_sync_all_campaigns_option() -> None:
    dummy_camps = [Path("/data/campaigns/roadmap"), Path("/data/campaigns/turboship")]
    with patch(
        "cocli.commands.smart_sync.get_all_campaign_dirs", return_value=dummy_camps
    ), patch("cocli.commands.smart_sync.sync_campaign_config") as mock_cfg, patch(
        "cocli.commands.smart_sync.sync_prospects"
    ) as mock_pros, patch(
        "cocli.commands.smart_sync.sync_emails"
    ) as mock_emails, patch(
        "cocli.commands.smart_sync.sync_queues"
    ) as mock_queues:
        result = runner.invoke(app, ["all", "-a"])
        assert result.exit_code == 0
        assert mock_cfg.call_count == 2
        assert mock_pros.call_count == 2
        assert mock_emails.call_count == 2
        assert mock_queues.call_count == 2


def test_smart_sync_all_campaigns_command() -> None:
    dummy_camps = [Path("/data/campaigns/roadmap")]
    with patch(
        "cocli.commands.smart_sync.get_all_campaign_dirs", return_value=dummy_camps
    ), patch("cocli.commands.smart_sync.sync_campaign_config") as mock_cfg, patch(
        "cocli.commands.smart_sync.sync_prospects"
    ) as mock_pros, patch(
        "cocli.commands.smart_sync.sync_emails"
    ) as mock_emails, patch(
        "cocli.commands.smart_sync.sync_queues"
    ) as mock_queues:
        result = runner.invoke(app, ["all-campaigns"])
        assert result.exit_code == 0
        mock_cfg.assert_called_once_with("roadmap")
        mock_pros.assert_called_once_with("roadmap", 20, False, False)
        mock_emails.assert_called_once_with("roadmap", 20, False, False)
        mock_queues.assert_called_once_with("roadmap", 20, False, False)
