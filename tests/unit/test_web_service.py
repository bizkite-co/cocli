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
