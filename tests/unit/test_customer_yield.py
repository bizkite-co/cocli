"""compile_customer_yield is the five-step fold, and it stops on a failed pull."""

from unittest.mock import MagicMock, patch

from cocli.application.customer_yield import compile_customer_yield
from cocli.application.lead_export_service import LeadExportResult
from cocli.application.pi_sync_service import SyncResult


def test_compile_yield_syncs_completed_queues_before_export(tmp_path) -> None:
    fake = LeadExportResult(
        campaign_name="turboship",
        exported_count=7,
        output_csv=tmp_path / "out.csv",
        output_usv=tmp_path / "out.usv",
    )
    with patch("cocli.application.pi_sync_service.PiSyncService") as pi, patch(
        "cocli.application.data_sync_service.DataSyncService"
    ) as data_sync, patch(
        "cocli.application.index_service.IndexService"
    ) as index, patch(
        "cocli.application.lead_export_service.export_enriched_emails",
        return_value=fake,
    ):
        pi.return_value.sync_completed.return_value = [
            SyncResult(host="cocli5x0", success=True, files_synced=4)
        ]
        pi.return_value.sync_email_indexes.return_value = [
            SyncResult(host="cocli5x0", success=True, files_synced=2)
        ]
        data_sync.return_value.compact_index.return_value = {"status": "success", "message": "ok"}
        index.return_value.compact.return_value = MagicMock(success=True, message="folded")
        result = compile_customer_yield("turboship")

    pi.return_value.sync_completed.assert_called_once()
    pi.return_value.sync_all_nodes.assert_not_called()
    assert result.exported_count == 7
    pi.return_value.sync_prospect_wal_to_s3.assert_not_called()


def test_compile_yield_stops_when_completed_queue_sync_fails() -> None:
    with patch("cocli.application.pi_sync_service.PiSyncService") as pi, patch(
        "cocli.application.lead_export_service.export_enriched_emails"
    ) as export:
        pi.return_value.sync_completed.return_value = [
            SyncResult(
                host="cocli5x0",
                success=False,
                files_synced=0,
                error="gm-list (completed/): rsync exited 30",
            )
        ]
        try:
            compile_customer_yield("turboship")
            raised = False
        except RuntimeError as exc:
            raised = True
            assert "Completed queue sync failed" in str(exc)
            assert "rsync exited 30" in str(exc)
    assert raised
    pi.return_value.sync_email_indexes.assert_not_called()
    export.assert_not_called()
