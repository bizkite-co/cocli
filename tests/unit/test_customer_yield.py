"""compile_customer_yield is the five-step fold, and it stops on a failed pull."""

import subprocess
from unittest.mock import MagicMock, patch

from cocli.application.customer_yield import compile_customer_yield
from cocli.application.lead_export_service import LeadExportResult
from cocli.application.pi_sync_service import SyncResult


def test_compile_yield_runs_pi_results_with_force_before_export(tmp_path) -> None:
    fake = LeadExportResult(
        campaign_name="turboship",
        exported_count=7,
        output_csv=tmp_path / "out.csv",
        output_usv=tmp_path / "out.usv",
    )
    with patch("subprocess.run", return_value=subprocess.CompletedProcess(args=[], returncode=0)) as run, patch(
        "cocli.application.pi_sync_service.PiSyncService"
    ) as pi, patch(
        "cocli.application.data_sync_service.DataSyncService"
    ) as data_sync, patch(
        "cocli.application.index_service.IndexService"
    ) as index, patch(
        "cocli.application.lead_export_service.export_enriched_emails",
        return_value=fake,
    ):
        pi.return_value.sync_email_indexes.return_value = [
            SyncResult(host="cocli5x0", success=True, files_synced=2)
        ]
        data_sync.return_value.compact_index.return_value = {"status": "success", "message": "ok"}
        index.return_value.compact.return_value = MagicMock(success=True, message="folded")
        result = compile_customer_yield("turboship")

    cmd = run.call_args.args[0]
    assert cmd[cmd.index("--campaign") :][:3] == ["--campaign", "turboship", "--force"]
    assert result.exported_count == 7
    pi.return_value.sync_prospect_wal_to_s3.assert_not_called()


def test_compile_yield_stops_when_pi_results_fails() -> None:
    with patch(
        "subprocess.run",
        side_effect=subprocess.CalledProcessError(1, ["cocli", "sync", "pi-results"]),
    ), patch("cocli.application.pi_sync_service.PiSyncService") as pi, patch(
        "cocli.application.lead_export_service.export_enriched_emails"
    ) as export:
        try:
            compile_customer_yield("turboship")
            raised = False
        except RuntimeError as exc:
            raised = True
            assert "Pi results sync failed" in str(exc)
    assert raised
    pi.assert_not_called()
    export.assert_not_called()
