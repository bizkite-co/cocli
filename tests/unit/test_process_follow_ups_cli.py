"""cocli campaign process-follow-ups must thread the campaign name into
FollowUpService.process_due() and report the result."""

from __future__ import annotations

from typer.testing import CliRunner

from cocli.application.follow_up_service import ProcessFollowUpsResult

runner = CliRunner()


def test_process_follow_ups_reports_result(cli_app, mocker) -> None:
    mock_service_cls = mocker.patch(
        "cocli.application.follow_up_service.FollowUpService"
    )
    mock_service = mock_service_cls.return_value
    mock_service.process_due.return_value = ProcessFollowUpsResult(
        due=3, calls_queued=1, emails_queued=2, errors=[]
    )

    result = runner.invoke(cli_app, ["campaign", "process-follow-ups", "roadmap"])

    assert result.exit_code == 0, result.output
    output = " ".join(result.output.split())
    assert "3 due" in output
    assert "1 call(s) queued" in output
    assert "2 email(s) rendered for review" in output
    mock_service_cls.assert_called_once_with("roadmap")
    mock_service.process_due.assert_called_once_with()


def test_process_follow_ups_prints_errors(cli_app, mocker) -> None:
    mock_service_cls = mocker.patch(
        "cocli.application.follow_up_service.FollowUpService"
    )
    mock_service = mock_service_cls.return_value
    mock_service.process_due.return_value = ProcessFollowUpsResult(
        due=1, calls_queued=0, emails_queued=0, errors=["bad-co: no eligible contact found"]
    )

    result = runner.invoke(cli_app, ["campaign", "process-follow-ups", "roadmap"])

    assert result.exit_code == 0, result.output
    assert "bad-co: no eligible contact found" in result.output
