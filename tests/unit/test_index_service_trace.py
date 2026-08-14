"""Unit tests for IndexService.trace_prospects: orchestrates the
prospect_trace station checks, including the one that needs cluster-node
resolution and SSH (kept out of cocli/core/ per the import-linter contract).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch


from cocli.application.index_service import IndexService, ProspectTraceResult
from cocli.core.paths import paths
from cocli.models.campaigns.worker_config import PiNodeConfig

US = "\x1f"


def _setup_campaign_dirs(tmp_path: Path, campaign: str = "test-campaign") -> None:
    paths.root = tmp_path
    campaign_dir = tmp_path / "campaigns" / campaign
    (campaign_dir / "indexes" / "google_maps_prospects").mkdir(parents=True)
    (campaign_dir / "queues" / "gm-list" / "completed" / "results").mkdir(parents=True)
    (campaign_dir / "queues" / "gm-details" / "completed").mkdir(parents=True)
    (campaign_dir / "queues" / "gm-details" / "pending").mkdir(parents=True)


def test_trace_prospects_assembles_full_pipeline_state(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    base = tmp_path / "campaigns" / campaign

    # PLACE_A: found by gm-list, gm-details completed, in checkpoint - healthy.
    (base / "queues" / "gm-list" / "completed" / "results" / "q.usv").write_text(
        f"PLACE_A{US}Name A\nPLACE_B{US}Name B\n"
    )
    (base / "queues" / "gm-details" / "completed" / "PLACE_A.json").write_text("{}")
    (base / "indexes" / "google_maps_prospects" / "prospects.usv").write_text(
        f"PLACE_A{US}rest\n"
    )

    # PLACE_B: found by gm-list, gm-details completed, but never made the
    # checkpoint and isn't in the (mocked) Pi WAL either - the WAL-write gap.
    (base / "queues" / "gm-details" / "completed" / "PLACE_B.json").write_text("{}")

    service = IndexService(campaign_name=campaign)

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x0", ip="10.0.0.1")],
    ), patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        result = service.trace_prospects(["PLACE_A", "PLACE_B"])

    assert isinstance(result, ProspectTraceResult)
    assert result.campaign_name == campaign
    rows = {r.place_id: r for r in result.rows}

    assert rows["PLACE_A"].gm_details == "completed"
    assert rows["PLACE_A"].checkpoint == "present"
    assert rows["PLACE_A"].verdict == "present in current checkpoint"

    assert rows["PLACE_B"].gm_details == "completed"
    assert rows["PLACE_B"].checkpoint == "absent"
    assert rows["PLACE_B"].pi_wal == "absent"
    assert "WAL-write or sync gap" in rows["PLACE_B"].verdict


def test_trace_prospects_uses_pi_wal_listing(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    base = tmp_path / "campaigns" / campaign
    (base / "queues" / "gm-details" / "completed" / "PLACE_C.json").write_text("{}")

    service = IndexService(campaign_name=campaign)

    def _fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(cmd, 0, stdout="PLACE_C.usv\n", stderr="")

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x0", ip="10.0.0.1")],
    ), patch("subprocess.run", side_effect=_fake_run):
        result = service.trace_prospects(["PLACE_C"])

    row = result.rows[0]
    assert row.pi_wal == "present"
    assert "FOLD BUG" in row.verdict


def test_trace_prospects_handles_no_cluster_nodes_gracefully(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    service = IndexService(campaign_name=campaign)

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        side_effect=RuntimeError("no config"),
    ):
        result = service.trace_prospects(["PLACE_X"])

    assert result.rows[0].pi_wal == "absent"
    assert "never rediscovered" in result.rows[0].verdict


def test_trace_prospects_empty_place_ids_returns_no_rows(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    service = IndexService(campaign_name=campaign)

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes", return_value=[]
    ):
        result = service.trace_prospects([])

    assert result.rows == []
