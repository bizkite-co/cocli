"""CLI-level tests for `cocli audit campaign`: whole-campaign leak audit.

Mirrors tests/unit/test_index_trace_command.py's pattern - mocks
ServiceContainer so these stay fast/offline, real coverage of the
underlying trace mechanism lives in test_prospect_trace.py and
test_index_service_trace.py.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cocli.application.index_service import ProspectTraceResult, ProspectTraceRow
from cocli.commands.audit import app
from cocli.core.paths import paths

runner = CliRunner()


def _fake_result(rows: list) -> ProspectTraceResult:
    return ProspectTraceResult(
        campaign_name="test-campaign", index_name="google_maps_prospects", rows=rows
    )


def test_audit_campaign_reports_gap_tally_and_writes_csv(tmp_path: Path) -> None:
    paths.root = tmp_path
    fake_container = MagicMock()
    fake_container.index_service.discover_all_place_ids.return_value = [
        "PLACE_A", "PLACE_B", "PLACE_C",
    ]
    fake_container.index_service.trace_prospects.return_value = _fake_result(
        [
            ProspectTraceRow(
                place_id="PLACE_A", gm_list="found", gm_details="completed",
                pi_wal="present", checkpoint="present", enrichment="completed",
                verdict="present in checkpoint, enrichment completed",
                gap_category="no gap",
            ),
            ProspectTraceRow(
                place_id="PLACE_B", gm_list="found", gm_details="completed",
                pi_wal="present", checkpoint="present", enrichment="never seen",
                verdict="present in checkpoint, never reached enrichment queue - enrichment-enqueue gap",
                gap_category="Identity Gap (enrichment-enqueue)",
            ),
            ProspectTraceRow(
                place_id="PLACE_C", gm_list="found", gm_details="completed",
                pi_wal="present", checkpoint="present", enrichment="no domain",
                verdict="present in checkpoint, no domain found yet - can't enrich",
                gap_category="no gap (pre-enrichment)",
            ),
        ]
    )

    with patch("cocli.commands.audit.get_campaign", return_value=None), \
         patch("cocli.application.services.ServiceContainer", return_value=fake_container):
        result = runner.invoke(app, ["campaign", "--campaign", "test-campaign"])

    assert result.exit_code == 0, result.output
    assert "Identity Gap (enrichment-enqueue)" in result.output
    assert "1" in result.output  # the one real gap
    fake_container.index_service.discover_all_place_ids.assert_called_once()
    fake_container.index_service.trace_prospects.assert_called_once_with(
        ["PLACE_A", "PLACE_B", "PLACE_C"]
    )

    export_dir = tmp_path / "campaigns" / "test-campaign" / "exports"
    csv_files = list(export_dir.glob("campaign_audit_*.csv"))
    assert len(csv_files) == 1
    content = csv_files[0].read_text()
    assert "PLACE_B" in content
    assert "Identity Gap (enrichment-enqueue)" in content


def test_audit_campaign_respects_limit(tmp_path: Path) -> None:
    paths.root = tmp_path
    fake_container = MagicMock()
    fake_container.index_service.discover_all_place_ids.return_value = [
        "PLACE_A", "PLACE_B", "PLACE_C",
    ]
    fake_container.index_service.trace_prospects.return_value = _fake_result(
        [
            ProspectTraceRow(
                place_id="PLACE_A", gm_list="found", gm_details="completed",
                pi_wal="present", checkpoint="present", enrichment="completed",
                verdict="present in checkpoint, enrichment completed",
                gap_category="no gap",
            ),
        ]
    )

    with patch("cocli.commands.audit.get_campaign", return_value=None), \
         patch("cocli.application.services.ServiceContainer", return_value=fake_container):
        result = runner.invoke(
            app, ["campaign", "--campaign", "test-campaign", "--limit", "1"]
        )

    assert result.exit_code == 0, result.output
    fake_container.index_service.trace_prospects.assert_called_once_with(["PLACE_A"])


def test_audit_campaign_no_place_ids_found(tmp_path: Path) -> None:
    paths.root = tmp_path
    fake_container = MagicMock()
    fake_container.index_service.discover_all_place_ids.return_value = []

    with patch("cocli.commands.audit.get_campaign", return_value=None), \
         patch("cocli.application.services.ServiceContainer", return_value=fake_container):
        result = runner.invoke(app, ["campaign", "--campaign", "test-campaign"])

    assert result.exit_code == 0, result.output
    assert "nothing to audit" in result.output.lower()
    fake_container.index_service.trace_prospects.assert_not_called()
