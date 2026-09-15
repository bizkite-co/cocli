"""cocli email send-batch --dry-run must preview without sending or logging."""

from __future__ import annotations

from typer.testing import CliRunner

from cocli.application.personalized_outreach_service import ProspectContactMatch

runner = CliRunner()


def test_send_batch_dry_run_does_not_send_or_write_log(cli_app, mocker) -> None:
    mocker.patch("cocli.commands.email.get_campaign", return_value="roadmap")

    match = ProspectContactMatch(
        company_slug="acme-financial",
        company_name="Acme Financial",
        recipient_email="bob@acme.test",
        contact_name="Bob Smith",
        first_name="Bob",
        role=None,
        subject="Hi Bob",
        body="body",
    )
    mock_service_cls = mocker.patch(
        "cocli.application.personalized_outreach_service.PersonalizedOutreachService"
    )
    mock_service = mock_service_cls.return_value
    mock_service.find_eligible_prospects.return_value = [match]

    result = runner.invoke(cli_app, ["email", "send-batch", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "Dry run" in result.output
    mock_service.send_batch.assert_not_called()
