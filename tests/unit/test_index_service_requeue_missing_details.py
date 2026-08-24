"""Unit tests for IndexService.requeue_missing_details: pushes a fresh
gm-details task built directly from the checkpoint, for place_ids with no
gm-details completed/pending record and no gm-list result file to fall
back on (unlike requeue_stuck_details).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from cocli.application.index_service import IndexService, RequeueResult
from cocli.core.paths import paths
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.models.campaigns.worker_config import PiNodeConfig

US = "\x1f"


def _all_ok_response(cmd: list, **kwargs) -> "subprocess.CompletedProcess":  # type: ignore[no-untyped-def,type-arg]
    import re

    script = kwargs.get("input", "")
    ids = re.findall(r"echo COCLI_OK:(\S+); else", script)
    stdout = "\n".join(f"COCLI_OK:{i}" for i in ids) + "\n"
    return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")


def _setup_campaign_dirs(tmp_path: Path, campaign: str = "test-campaign") -> None:
    paths.root = tmp_path
    campaign_dir = tmp_path / "campaigns" / campaign
    (campaign_dir / "indexes" / "google_maps_prospects").mkdir(parents=True)
    (campaign_dir / "queues" / "gm-details" / "completed").mkdir(parents=True)
    (campaign_dir / "queues" / "gm-details" / "pending").mkdir(parents=True)


def _checkpoint_row(
    place_id: str, name: str = "", slug: str = "", category: str = "", gmb_url: str = ""
) -> str:
    fieldnames = list(GoogleMapsProspect.model_fields.keys())
    values = {f: "" for f in fieldnames}
    values["place_id"] = place_id
    values["name"] = name
    values["slug"] = slug
    values["category"] = category
    values["gmb_url"] = gmb_url
    return US.join(values[f] for f in fieldnames)


def test_requeue_missing_details_pushes_via_single_ssh_call(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    base = tmp_path / "campaigns" / campaign
    (base / "indexes" / "google_maps_prospects" / "prospects.usv").write_text(
        _checkpoint_row("PLACE_A", "Acme A", "acme-a", "Flooring store", "https://maps.google.com/a") + "\n"
        + _checkpoint_row("PLACE_B", "Acme B", "acme-b", "Carpet installer", "https://maps.google.com/b") + "\n"
    )

    service = IndexService(campaign_name=campaign)

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x0", ip="10.0.0.1")],
    ), patch("subprocess.run") as mock_run:
        mock_run.side_effect = _all_ok_response
        result = service.requeue_missing_details(["PLACE_A", "PLACE_B"])

    assert isinstance(result, RequeueResult)
    statuses = {r.place_id: r.status for r in result.rows}
    assert statuses == {"PLACE_A": "requeued", "PLACE_B": "requeued"}

    mock_run.assert_called_once()
    call_args = mock_run.call_args
    assert call_args[0][0][:3] == ["ssh", "-o", "ConnectTimeout=15"]
    script = call_args[1]["input"]
    assert "PLACE_A" in script
    assert "PLACE_B" in script
    assert script.count("mkdir -p") == 2


def test_requeue_missing_details_skips_no_gmb_url(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    base = tmp_path / "campaigns" / campaign
    (base / "indexes" / "google_maps_prospects" / "prospects.usv").write_text(
        _checkpoint_row("PLACE_NO_GMB", "No GMB Inc", "no-gmb-inc") + "\n"
    )

    service = IndexService(campaign_name=campaign)

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x0", ip="10.0.0.1")],
    ), patch("subprocess.run") as mock_run:
        result = service.requeue_missing_details(["PLACE_NO_GMB"])

    assert result.rows[0].status == "not_found"
    assert "gmb_url" in result.rows[0].detail
    mock_run.assert_not_called()


def test_requeue_missing_details_skips_place_id_not_in_checkpoint(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    base = tmp_path / "campaigns" / campaign
    (base / "indexes" / "google_maps_prospects" / "prospects.usv").write_text(
        _checkpoint_row("PLACE_A", "Acme A", "acme-a", "Flooring store", "https://maps.google.com/a") + "\n"
    )

    service = IndexService(campaign_name=campaign)

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x0", ip="10.0.0.1")],
    ), patch("subprocess.run") as mock_run:
        result = service.requeue_missing_details(["PLACE_UNKNOWN"])

    assert result.rows[0].status == "not_found"
    mock_run.assert_not_called()


def test_requeue_missing_details_skips_already_completed(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    base = tmp_path / "campaigns" / campaign
    (base / "indexes" / "google_maps_prospects" / "prospects.usv").write_text(
        _checkpoint_row("PLACE_DONE", "Done Inc", "done-inc", "Flooring store", "https://maps.google.com/done") + "\n"
    )
    (base / "queues" / "gm-details" / "completed" / "PLACE_DONE.json").write_text("{}")

    service = IndexService(campaign_name=campaign)

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x0", ip="10.0.0.1")],
    ), patch("subprocess.run") as mock_run:
        result = service.requeue_missing_details(["PLACE_DONE"])

    assert result.rows[0].status == "skipped"
    assert "already completed" in result.rows[0].detail
    mock_run.assert_not_called()


def test_requeue_missing_details_ssh_failure_marks_error(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    base = tmp_path / "campaigns" / campaign
    (base / "indexes" / "google_maps_prospects" / "prospects.usv").write_text(
        _checkpoint_row("PLACE_A", "Acme A", "acme-a", "Flooring store", "https://maps.google.com/a") + "\n"
    )

    service = IndexService(campaign_name=campaign)

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x0", ip="10.0.0.1")],
    ), patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess([], 1, stdout="", stderr="permission denied")
        result = service.requeue_missing_details(["PLACE_A"])

    assert result.rows[0].status == "ssh_error"
    assert "permission denied" in result.rows[0].detail


def test_requeue_missing_details_one_bad_record_does_not_fail_the_batch(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    base = tmp_path / "campaigns" / campaign
    (base / "indexes" / "google_maps_prospects" / "prospects.usv").write_text(
        _checkpoint_row("PLACE_GOOD", "Good Inc", "good-inc", "Flooring store", "https://maps.google.com/good") + "\n"
        + _checkpoint_row("PLACE_BAD", "Bad Inc", "bad-inc", "Flooring store", "https://maps.google.com/bad") + "\n"
    )

    service = IndexService(campaign_name=campaign)

    def _one_fails(cmd, **kwargs):  # type: ignore[no-untyped-def]
        stdout = "COCLI_OK:PLACE_GOOD\nCOCLI_FAIL:PLACE_BAD\n"
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x0", ip="10.0.0.1")],
    ), patch("subprocess.run", side_effect=_one_fails):
        result = service.requeue_missing_details(["PLACE_GOOD", "PLACE_BAD"])

    statuses = {r.place_id: r.status for r in result.rows}
    assert statuses["PLACE_GOOD"] == "requeued"
    assert statuses["PLACE_BAD"] == "ssh_error"


def test_requeue_missing_details_uses_sudo(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    base = tmp_path / "campaigns" / campaign
    (base / "indexes" / "google_maps_prospects" / "prospects.usv").write_text(
        _checkpoint_row("PLACE_A", "Acme A", "acme-a", "Flooring store", "https://maps.google.com/a") + "\n"
    )

    service = IndexService(campaign_name=campaign)

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x0", ip="10.0.0.1")],
    ), patch("subprocess.run") as mock_run:
        mock_run.side_effect = _all_ok_response
        service.requeue_missing_details(["PLACE_A"])

    script = mock_run.call_args[1]["input"]
    assert "sudo mkdir -p" in script
    assert "sudo tee" in script


def test_requeue_missing_details_pushed_payload_is_valid_json(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    base = tmp_path / "campaigns" / campaign
    (base / "indexes" / "google_maps_prospects" / "prospects.usv").write_text(
        _checkpoint_row("PLACE_A", "Acme A", "acme-a", "Flooring store", "https://maps.google.com/a") + "\n"
    )

    service = IndexService(campaign_name=campaign)

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x0", ip="10.0.0.1")],
    ), patch("subprocess.run") as mock_run:
        mock_run.side_effect = _all_ok_response
        service.requeue_missing_details(["PLACE_A"])

    script = mock_run.call_args[1]["input"]
    lines = script.splitlines()
    heredoc_line_idx = next(
        i for i, line in enumerate(lines) if "sudo tee" in line and "task.json" in line
    )
    payload = json.loads(lines[heredoc_line_idx + 1])
    assert payload["place_id"] == "PLACE_A"
    assert payload["name"] == "Acme A"
    assert payload["company_slug"] == "acme-a"
    assert payload["gmb_url"] == "https://maps.google.com/a"
    assert "category" not in payload
    assert payload["campaign_name"] == campaign


def test_requeue_missing_details_batches_across_multiple_ssh_calls(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    base = tmp_path / "campaigns" / campaign
    rows = "\n".join(
        _checkpoint_row(f"PLACE_{i}", f"Co {i}", f"co-{i}", "Flooring store", f"https://maps.google.com/{i}")
        for i in range(5)
    )
    (base / "indexes" / "google_maps_prospects" / "prospects.usv").write_text(rows + "\n")

    service = IndexService(campaign_name=campaign)
    ids = [f"PLACE_{i}" for i in range(5)]

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x0", ip="10.0.0.1")],
    ), patch("subprocess.run") as mock_run:
        mock_run.side_effect = _all_ok_response
        result = service.requeue_missing_details(ids, batch_size=2)

    assert mock_run.call_count == 3  # 2 + 2 + 1
    assert all(r.status == "requeued" for r in result.rows)
