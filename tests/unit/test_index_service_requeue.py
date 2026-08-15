"""Unit tests for IndexService.requeue_stuck_details: recovers gm-details
tasks that were acked with no WAL entry (the gm-details-acks-unconditionally
incident). Writes go over SSH directly to each Pi node, since gm-details'
pending/ directory never syncs Pi<->dev-machine.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from cocli.application.index_service import IndexService, RequeueResult
from cocli.core.paths import paths
from cocli.models.campaigns.worker_config import PiNodeConfig

US = "\x1f"


def _setup_campaign_dirs(tmp_path: Path, campaign: str = "test-campaign") -> None:
    paths.root = tmp_path
    campaign_dir = tmp_path / "campaigns" / campaign
    (campaign_dir / "queues" / "gm-list" / "completed" / "results").mkdir(parents=True)
    (campaign_dir / "queues" / "gm-details" / "completed").mkdir(parents=True)


def _write_completed_marker(
    tmp_path: Path, campaign: str, place_id: str, **fields: object
) -> Path:
    marker = (
        tmp_path / "campaigns" / campaign / "queues" / "gm-details" / "completed"
        / f"{place_id}.json"
    )
    payload = {
        "place_id": place_id,
        "campaign_name": campaign,
        "name": "Affordable Carpet & Wood",
        "company_slug": "affordable-carpet-wood",
        "force_refresh": True,
        "discovery_phrase": None,
        "discovery_tile_id": None,
        "attempts": 3,
        **fields,
    }
    marker.write_text(json.dumps(payload))
    return marker


def test_requeue_uses_local_completed_marker_as_primary_source(tmp_path: Path) -> None:
    """The stale completed marker is the original task, already synced
    locally - it must be preferred over reconstructing from a gm-list row,
    and a fresh push must reset attempts (a new attempt, not a
    continuation)."""
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    _write_completed_marker(tmp_path, campaign, "PLACE_A")

    service = IndexService(campaign_name=campaign)
    calls = []

    def _fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        calls.append((cmd, kwargs.get("input")))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x0", ip="10.0.0.1")],
    ), patch("subprocess.run", side_effect=_fake_run):
        result = service.requeue_stuck_details(["PLACE_A"])

    assert result.rows[0].status == "requeued"
    push_cmd, push_input = calls[0]
    assert push_input is not None
    pushed = json.loads(push_input)
    assert pushed["name"] == "Affordable Carpet & Wood"
    assert pushed["company_slug"] == "affordable-carpet-wood"
    assert pushed["attempts"] == 0


def test_requeue_falls_back_to_gm_list_when_no_local_marker(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    base = tmp_path / "campaigns" / campaign
    (base / "queues" / "gm-list" / "completed" / "results" / "q.usv").write_text(
        f"PLACE_A{US}slug-a{US}Name A{US}Category A{US}\n"
    )

    service = IndexService(campaign_name=campaign)

    calls = []

    def _fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        calls.append((cmd, kwargs.get("input")))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x0", ip="10.0.0.1")],
    ), patch("subprocess.run", side_effect=_fake_run):
        result = service.requeue_stuck_details(["PLACE_A"])

    assert isinstance(result, RequeueResult)
    assert result.rows[0].place_id == "PLACE_A"
    assert result.rows[0].status == "requeued"
    assert "cocli5x0" in result.rows[0].detail

    # Write-then-delete order: the pending task must be written and
    # confirmed *before* the stale completed marker is removed, so a
    # mid-way failure never leaves a record with no trace at all.
    assert len(calls) == 2
    push_cmd, push_input = calls[0]
    rm_cmd, _ = calls[1]
    assert "pending" in push_cmd[-1]
    assert "PLACE_A" in push_cmd[-1]
    assert push_input is not None
    assert "PLACE_A" in push_input
    assert "rm -f" in rm_cmd[-1]
    assert "PLACE_A.json" in rm_cmd[-1]


def test_requeue_falls_back_to_gm_list_when_marker_unparseable(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    base = tmp_path / "campaigns" / campaign
    (base / "queues" / "gm-list" / "completed" / "results" / "q.usv").write_text(
        f"PLACE_A{US}slug-a{US}Name A{US}\n"
    )
    marker = (
        base / "queues" / "gm-details" / "completed" / "PLACE_A.json"
    )
    marker.write_text("{not valid json")

    service = IndexService(campaign_name=campaign)

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x0", ip="10.0.0.1")],
    ), patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        result = service.requeue_stuck_details(["PLACE_A"])

    assert result.rows[0].status == "requeued"


def test_requeue_reports_not_found_when_no_marker_and_no_gm_list_row(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    service = IndexService(campaign_name=campaign)

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x0", ip="10.0.0.1")],
    ):
        result = service.requeue_stuck_details(["PLACE_MISSING"])

    assert result.rows[0].status == "not_found"


def test_requeue_reports_ssh_error_when_no_cluster_nodes(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    _write_completed_marker(tmp_path, campaign, "PLACE_A")

    service = IndexService(campaign_name=campaign)

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        side_effect=RuntimeError("no config"),
    ):
        result = service.requeue_stuck_details(["PLACE_A"])

    assert result.rows[0].status == "ssh_error"


def test_requeue_reports_ssh_error_when_all_nodes_fail(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    _write_completed_marker(tmp_path, campaign, "PLACE_A")

    service = IndexService(campaign_name=campaign)

    def _fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        if "cat >" in cmd[-1]:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="permission denied")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x0", ip="10.0.0.1")],
    ), patch("subprocess.run", side_effect=_fake_run):
        result = service.requeue_stuck_details(["PLACE_A"])

    assert result.rows[0].status == "ssh_error"
    assert "permission denied" in result.rows[0].detail


def test_requeue_pushes_to_one_node_but_clears_marker_on_all(tmp_path: Path) -> None:
    """With multiple nodes, only one should receive the fresh pending task
    (otherwise N workers race to scrape the same place_id), but the stale
    completed marker must be cleared everywhere since it's unknown which
    node originally produced it."""
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    _write_completed_marker(tmp_path, campaign, "PLACE_A")

    service = IndexService(campaign_name=campaign)

    calls = []

    def _fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    nodes = [
        PiNodeConfig(host="cocli5x0", ip="10.0.0.1"),
        PiNodeConfig(host="cocli5x1", ip="10.0.0.2"),
    ]

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes", return_value=nodes
    ), patch("subprocess.run", side_effect=_fake_run):
        result = service.requeue_stuck_details(["PLACE_A"])

    assert result.rows[0].status == "requeued"

    push_calls = [c for c in calls if "pending" in c[-1] and "cat >" in c[-1]]
    rm_calls = [c for c in calls if "rm -f" in c[-1]]
    assert len(push_calls) == 1
    assert len(rm_calls) == 2
    push_targets = {c[3].split("@")[1] for c in push_calls}
    rm_targets = {c[3].split("@")[1] for c in rm_calls}
    assert push_targets == {"10.0.0.1"}
    assert rm_targets == {"10.0.0.1", "10.0.0.2"}


def test_requeue_empty_place_ids_returns_no_rows(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    service = IndexService(campaign_name=campaign)

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes", return_value=[]
    ):
        result = service.requeue_stuck_details([])

    assert result.rows == []
