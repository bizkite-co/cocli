from pathlib import Path
from unittest.mock import MagicMock, patch

import toml
from cocli.core.paths import paths
from cocli.application.lead_export_service import LeadExportResult
from cocli.application.web_service import WebService

def test_web_service_resolve_deployment_config(tmp_path):
    # Set up isolated paths
    paths.root = tmp_path
    campaign_name = "test-campaign"
    campaign_dir = tmp_path / "campaigns" / campaign_name
    campaign_dir.mkdir(parents=True)

    # Create config.toml
    config_data = {
        "aws": {
            "profile": "test-profile",
            "hosted-zone-domain": "test-domain.com"
        }
    }
    with open(campaign_dir / "config.toml", "w") as f:
        toml.dump(config_data, f)

    service = WebService(campaign_name=campaign_name)
    cfg = service.resolve_deployment_config()

    assert cfg["profile"] == "test-profile"
    assert cfg["domain"] == "cocli.test-domain.com"
    assert cfg["bucket_name"] == "cocli-web-assets-test-domain-com"


def test_export_and_upload_emails_csv_uploads_usv_and_csv_with_download_headers(tmp_path):
    """Regression (Mark, 2026-09-01): the customer-facing CSV export/upload
    was only reachable via the full `cocli web deploy` (site rebuild + CDK
    fetch + shell sync), so refreshing just the CSV meant paying for all of
    that too. Extracted so a narrower `cocli web export-emails` command can
    run this on its own - verify the shared method still uploads both
    artifacts with the same S3 keys/headers `web deploy` always used."""
    service = WebService(campaign_name="test-campaign")
    fake_result = LeadExportResult(
        campaign_name="test-campaign",
        exported_count=3,
        output_usv=tmp_path / "test-campaign-emails.usv",
        output_csv=tmp_path / "test-campaign-emails.csv",
    )
    fake_result.output_usv.write_text("data")
    fake_result.output_csv.write_text("data")

    mock_s3 = MagicMock()

    with patch("subprocess.run"), patch(
        "cocli.application.pi_sync_service.PiSyncService"
    ) as mock_pi_sync, patch(
        "cocli.application.index_service.IndexService"
    ) as mock_index_service, patch(
        "cocli.application.lead_export_service.export_enriched_emails",
        return_value=fake_result,
    ):
        mock_pi_sync.return_value.sync_prospect_wal_to_s3.return_value = []
        mock_index_service.return_value.compact.return_value = MagicMock(success=True)

        result = service.export_and_upload_emails_csv(mock_s3, "test-bucket")

    assert result.exported_count == 3
    assert mock_s3.upload_file.call_count == 2

    usv_call = mock_s3.upload_file.call_args_list[0]
    assert usv_call.args[1:] == ("test-bucket", "exports/test-campaign-emails.usv")

    csv_call = mock_s3.upload_file.call_args_list[1]
    assert csv_call.args[1:] == ("test-bucket", "exports/test-campaign-emails.csv")
    assert csv_call.kwargs["ExtraArgs"]["ContentType"] == "text/csv"
    assert (
        csv_call.kwargs["ExtraArgs"]["ContentDisposition"]
        == 'attachment; filename="test-campaign-emails.csv"'
    )


def test_web_deploy_shell_only_skips_emails_reports_and_kml(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from cocli.commands.web import app as web_app

    campaign_dir = tmp_path / "campaigns" / "ship"
    campaign_dir.mkdir(parents=True)
    (campaign_dir / "config.toml").write_text("")

    mock_web = MagicMock()
    mock_web.resolve_deployment_config.return_value = {
        "profile": "p",
        "domain": "cocli.example.com",
        "bucket_name": "web-bucket",
    }
    mock_web.fetch_cdk_outputs.return_value = {}
    mock_services = MagicMock()
    mock_services.web_service = mock_web

    mock_session = MagicMock()
    mock_s3 = MagicMock()
    mock_cf = MagicMock()
    mock_session.client.side_effect = lambda name: mock_s3 if name == "s3" else mock_cf
    mock_cf.list_distributions.return_value = {
        "DistributionList": {
            "Items": [{"Id": "DIST1", "Aliases": {"Items": ["cocli.example.com"]}}]
        }
    }

    runner = CliRunner()
    with patch("cocli.commands.web.get_campaign", return_value="ship"), patch(
        "cocli.commands.web.get_campaign_dir", return_value=campaign_dir
    ), patch(
        "cocli.commands.web.ServiceContainer", return_value=mock_services
    ), patch(
        "cocli.commands.web.boto3.Session", return_value=mock_session
    ), patch(
        "cocli.commands.web.subprocess.run"
    ) as mock_run:
        result = runner.invoke(
            web_app,
            ["deploy", "--shell-only", "--campaign", "ship"],
        )

    assert result.exit_code == 0, result.output
    assert "Shell-only deploy complete" in result.output
    mock_web.export_and_upload_emails_csv.assert_not_called()
    mock_web.get_campaign_reports.assert_not_called()
    kml_calls = [
        c
        for c in mock_run.call_args_list
        if c.args and "publish-kml" in c.args[0]
    ]
    assert kml_calls == []
    mock_cf.create_invalidation.assert_called_once()
    paths = mock_cf.create_invalidation.call_args.kwargs["InvalidationBatch"]["Paths"]["Items"]
    assert paths == ["/kml-viewer.html"]
