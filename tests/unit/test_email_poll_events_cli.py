"""cocli email poll-events must thread campaign/region correctly into
EmailEventsService and report its result."""

from __future__ import annotations

from typer.testing import CliRunner

from cocli.application.email_events_service import PollEventsResult

runner = CliRunner()


def test_poll_events_reports_result(cli_app, mocker) -> None:
    mocker.patch("cocli.commands.email.get_campaign", return_value="roadmap")
    mocker.patch(
        "cocli.commands.email.load_campaign_config",
        return_value={"email": {"ses_region": "us-west-1"}, "aws": {"profile": "westmonroe-support"}},
    )
    mock_service_cls = mocker.patch("cocli.application.email_events_service.EmailEventsService")
    mock_service = mock_service_cls.return_value
    mock_service.poll.return_value = PollEventsResult(
        fetched=2, recorded=1, ignored=1, suppressed=["bad@co.test"]
    )

    result = runner.invoke(cli_app, ["email", "poll-events", "--limit", "5"])

    assert result.exit_code == 0, result.output
    assert "fetched=2" in result.output
    assert "recorded=1" in result.output
    mock_service_cls.assert_called_once_with("roadmap", region="us-west-1", profile="westmonroe-support")
    mock_service.poll.assert_called_once_with(limit=5)
