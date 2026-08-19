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


def _all_ok_response(cmd: list, **kwargs) -> "subprocess.CompletedProcess":  # type: ignore[no-untyped-def,type-arg]
    """Fakes a successful remote write: emits a COCLI_OK marker for every
    domain the real script would have tried to push (parsed straight out
    of the generated `echo COCLI_OK:<domain>; else echo COCLI_FAIL` lines),
    matching the per-record marker protocol requeue_enrichment_gaps()
    actually relies on now (a bare returncode=0 with empty stdout means
    "no per-record markers seen," i.e. everything failed)."""
    import re

    script = kwargs.get("input", "")
    domains = re.findall(r"echo COCLI_OK:(\S+); else", script)
    stdout = "\n".join(f"COCLI_OK:{d}" for d in domains) + "\n"
    return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")


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
        mock_run.side_effect = _all_ok_response
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
        mock_run.side_effect = _all_ok_response
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
        mock_run.side_effect = _all_ok_response
        service.requeue_enrichment_gaps(["PLACE_A"])

    script = mock_run.call_args[1]["input"]
    # The line right after the heredoc-open line is the JSON payload.
    lines = script.splitlines()
    heredoc_line_idx = next(
        i for i, line in enumerate(lines) if "sudo tee" in line and "task.json" in line
    )
    payload = json.loads(lines[heredoc_line_idx + 1])
    assert payload["domain"] == "example-a.com"
    assert payload["company_slug"] == "example-a-inc"
    assert payload["campaign_name"] == campaign
    assert payload["force_refresh"] is False


def test_requeue_enrichment_gaps_uses_sudo(tmp_path: Path) -> None:
    """Confirmed live 2026-08-18: some pending dirs are stale, root-owned
    leftovers from the containerized worker (which runs as root), while
    this SSH session runs as an unprivileged user - plain mkdir/cat gets
    Permission Denied on those. sudo is confirmed passwordless on the Pi
    nodes."""
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
        mock_run.side_effect = _all_ok_response
        service.requeue_enrichment_gaps(["PLACE_A"])

    script = mock_run.call_args[1]["input"]
    assert "sudo mkdir -p" in script
    assert "sudo tee" in script


def test_requeue_enrichment_gaps_one_bad_record_does_not_fail_the_batch(tmp_path: Path) -> None:
    """The real bug found live 2026-08-18: a batch of 1,667 records hit one
    stale, root-owned pending dir partway through and (under the old
    set -e script) the whole batch was marked ssh_error, discarding every
    write that had already succeeded. Now each record is isolated - a
    COCLI_FAIL for one domain must not affect any other domain's result."""
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    base = tmp_path / "campaigns" / campaign
    (base / "indexes" / "google_maps_prospects" / "prospects.usv").write_text(
        _checkpoint_row("PLACE_GOOD", "good.com", "good-inc") + "\n"
        + _checkpoint_row("PLACE_BAD", "bad.com", "bad-inc") + "\n"
    )

    service = IndexService(campaign_name=campaign)

    def _one_fails(cmd, **kwargs):  # type: ignore[no-untyped-def]
        # returncode=0 overall (bash never aborts - no set -e), but bad.com
        # reports FAIL while good.com reports OK, exactly like a real
        # Permission Denied on one specific stale directory.
        stdout = "COCLI_OK:good.com\nCOCLI_FAIL:bad.com\n"
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x0", ip="10.0.0.1")],
    ), patch("subprocess.run", side_effect=_one_fails):
        result = service.requeue_enrichment_gaps(["PLACE_GOOD", "PLACE_BAD"])

    statuses = {r.place_id: r.status for r in result.rows}
    assert statuses["PLACE_GOOD"] == "requeued"
    assert statuses["PLACE_BAD"] == "ssh_error"
