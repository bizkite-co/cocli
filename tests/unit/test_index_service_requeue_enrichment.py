"""Unit tests for IndexService.requeue_enrichment_gaps: recovers the
"Identity Gap (enrichment-enqueue)" gap cocli audit campaign finds.
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


def _setup_campaign_dirs(tmp_path: Path, campaign: str = "test-campaign") -> None:
    paths.root = tmp_path
    campaign_dir = tmp_path / "campaigns" / campaign
    (campaign_dir / "indexes" / "google_maps_prospects").mkdir(parents=True)
    (campaign_dir / "queues" / "enrichment" / "completed").mkdir(parents=True)
    (campaign_dir / "queues" / "enrichment" / "pending").mkdir(parents=True)


def _checkpoint_row(place_id: str, domain: str, slug: str) -> str:
    fieldnames = list(GoogleMapsProspect.model_fields.keys())
    values = {name: "" for name in fieldnames}
    values["place_id"] = place_id
    values["domain"] = domain
    values["slug"] = slug
    return US.join(values[name] for name in fieldnames)


def test_requeue_enrichment_gaps_pushes_via_single_ssh_call(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    base = tmp_path / "campaigns" / campaign
    (base / "indexes" / "google_maps_prospects" / "prospects.usv").write_text(
        _checkpoint_row("PLACE_A", "example-a.com", "example-a-inc") + "\n"
        + _checkpoint_row("PLACE_B", "example-b.com", "example-b-llc") + "\n"
    )

    service = IndexService(campaign_name=campaign)

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x0", ip="10.0.0.1")],
    ), patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        result = service.requeue_enrichment_gaps(["PLACE_A", "PLACE_B"])

    assert isinstance(result, RequeueResult)
    statuses = {r.place_id: r.status for r in result.rows}
    assert statuses == {"PLACE_A": "requeued", "PLACE_B": "requeued"}

    # Exactly one SSH call, not one per record.
    mock_run.assert_called_once()
    call_args = mock_run.call_args
    assert call_args[0][0][:3] == ["ssh", "-o", "ConnectTimeout=15"]
    script = call_args[1]["input"]
    assert "example-a.com" in script
    assert "example-b.com" in script
    assert script.count("mkdir -p") == 2


def test_requeue_enrichment_gaps_skips_no_domain(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    base = tmp_path / "campaigns" / campaign
    (base / "indexes" / "google_maps_prospects" / "prospects.usv").write_text(
        _checkpoint_row("PLACE_NO_DOMAIN", "", "some-slug") + "\n"
    )

    service = IndexService(campaign_name=campaign)

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x0", ip="10.0.0.1")],
    ), patch("subprocess.run") as mock_run:
        result = service.requeue_enrichment_gaps(["PLACE_NO_DOMAIN"])

    assert result.rows[0].status == "not_found"
    assert "no domain" in result.rows[0].detail
    mock_run.assert_not_called()


def test_requeue_enrichment_gaps_skips_already_enriched(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    base = tmp_path / "campaigns" / campaign
    (base / "indexes" / "google_maps_prospects" / "prospects.usv").write_text(
        _checkpoint_row("PLACE_DONE", "already-done.com", "already-done") + "\n"
    )
    (base / "queues" / "enrichment" / "completed" / "already-done.com.json").write_text("{}")

    service = IndexService(campaign_name=campaign)

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x0", ip="10.0.0.1")],
    ), patch("subprocess.run") as mock_run:
        result = service.requeue_enrichment_gaps(["PLACE_DONE"])

    assert result.rows[0].status == "skipped"
    assert "already completed" in result.rows[0].detail
    mock_run.assert_not_called()


def test_requeue_enrichment_gaps_dedupes_shared_domain(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    base = tmp_path / "campaigns" / campaign
    (base / "indexes" / "google_maps_prospects" / "prospects.usv").write_text(
        _checkpoint_row("PLACE_A", "shared.com", "shared-a") + "\n"
        + _checkpoint_row("PLACE_B", "shared.com", "shared-b") + "\n"
    )

    service = IndexService(campaign_name=campaign)

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x0", ip="10.0.0.1")],
    ), patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        result = service.requeue_enrichment_gaps(["PLACE_A", "PLACE_B"])

    statuses = {r.place_id: r.status for r in result.rows}
    assert statuses["PLACE_A"] == "requeued"
    assert statuses["PLACE_B"] == "skipped"
    script = mock_run.call_args[1]["input"]
    assert script.count("mkdir -p") == 1  # only pushed once, despite 2 place_ids


def test_requeue_enrichment_gaps_ssh_failure_marks_error(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    base = tmp_path / "campaigns" / campaign
    (base / "indexes" / "google_maps_prospects" / "prospects.usv").write_text(
        _checkpoint_row("PLACE_A", "example-a.com", "example-a-inc") + "\n"
    )

    service = IndexService(campaign_name=campaign)

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x0", ip="10.0.0.1")],
    ), patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess([], 1, stdout="", stderr="permission denied")
        result = service.requeue_enrichment_gaps(["PLACE_A"])

    assert result.rows[0].status == "ssh_error"
    assert "permission denied" in result.rows[0].detail


def test_requeue_enrichment_gaps_pushed_payload_is_valid_json(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    base = tmp_path / "campaigns" / campaign
    (base / "indexes" / "google_maps_prospects" / "prospects.usv").write_text(
        _checkpoint_row("PLACE_A", "example-a.com", "example-a-inc") + "\n"
    )

    service = IndexService(campaign_name=campaign)

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x0", ip="10.0.0.1")],
    ), patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        service.requeue_enrichment_gaps(["PLACE_A"])

    script = mock_run.call_args[1]["input"]
    # The line right after the heredoc-open line is the JSON payload.
    lines = script.splitlines()
    heredoc_line_idx = next(
        i for i, line in enumerate(lines) if line.startswith("cat > ") and "task.json" in line
    )
    payload = json.loads(lines[heredoc_line_idx + 1])
    assert payload["domain"] == "example-a.com"
    assert payload["company_slug"] == "example-a-inc"
    assert payload["campaign_name"] == campaign
    assert payload["force_refresh"] is False
