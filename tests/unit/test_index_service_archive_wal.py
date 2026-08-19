"""Unit tests for IndexService.archive_incomplete_schema_wal."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

from cocli.application.index_service import ArchiveWalResult, IndexService
from cocli.models.campaigns.worker_config import PiNodeConfig


def _fake_result(stdout: str, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:  # type: ignore[type-arg]
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


def test_archive_dry_run_reports_counts_without_mock_error() -> None:
    service = IndexService(campaign_name="test-campaign")

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x1", ip="10.0.0.2")],
    ), patch("subprocess.run") as mock_run:
        mock_run.return_value = _fake_result("COCLI_ARCHIVE_RESULT archived=24227 kept=7594\n")
        result = service.archive_incomplete_schema_wal(dry_run=True)

    assert isinstance(result, ArchiveWalResult)
    assert result.dry_run is True
    assert result.total_archived == 24227
    assert result.total_kept == 7594
    assert result.nodes[0].hostname == "cocli5x1"
    assert result.nodes[0].error == ""

    # dry_run=True must be passed through into the remote script.
    script = mock_run.call_args[1]["input"]
    assert "dry_run = True" in script


def test_archive_apply_passes_dry_run_false_to_remote_script() -> None:
    service = IndexService(campaign_name="test-campaign")

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x1", ip="10.0.0.2")],
    ), patch("subprocess.run") as mock_run:
        mock_run.return_value = _fake_result("COCLI_ARCHIVE_RESULT archived=5 kept=2\n")
        result = service.archive_incomplete_schema_wal(dry_run=False)

    assert result.dry_run is False
    script = mock_run.call_args[1]["input"]
    assert "dry_run = False" in script
    # sudo -n (non-interactive) so a missing passwordless-sudo config fails
    # fast instead of hanging on a password prompt.
    assert mock_run.call_args[0][0][-1] == "sudo -n python3 -"


def test_archive_runs_against_every_enabled_node() -> None:
    service = IndexService(campaign_name="test-campaign")

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[
            PiNodeConfig(host="cocli5x0", ip="10.0.0.1"),
            PiNodeConfig(host="cocli5x1", ip="10.0.0.2"),
        ],
    ), patch("subprocess.run") as mock_run:
        mock_run.return_value = _fake_result("COCLI_ARCHIVE_RESULT archived=1 kept=1\n")
        result = service.archive_incomplete_schema_wal(dry_run=True)

    assert mock_run.call_count == 2
    assert {n.hostname for n in result.nodes} == {"cocli5x0", "cocli5x1"}
    assert result.total_archived == 2
    assert result.total_kept == 2


def test_archive_records_error_when_no_result_line_seen() -> None:
    service = IndexService(campaign_name="test-campaign")

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x1", ip="10.0.0.2")],
    ), patch("subprocess.run") as mock_run:
        mock_run.return_value = _fake_result("", returncode=1, stderr="sudo: a password is required")
        result = service.archive_incomplete_schema_wal(dry_run=True)

    assert result.nodes[0].archived == 0
    assert "password is required" in result.nodes[0].error


def test_archive_timeout_records_error() -> None:
    service = IndexService(campaign_name="test-campaign")

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x1", ip="10.0.0.2")],
    ), patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ssh", timeout=180)):
        result = service.archive_incomplete_schema_wal(dry_run=True)

    assert result.nodes[0].error == "timeout"


def test_archive_no_nodes_returns_empty_result() -> None:
    service = IndexService(campaign_name="test-campaign")

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes", return_value=[]
    ), patch("subprocess.run") as mock_run:
        result = service.archive_incomplete_schema_wal(dry_run=True)

    assert result.nodes == []
    assert result.total_archived == 0
    mock_run.assert_not_called()


def test_archive_required_field_count_is_configurable() -> None:
    service = IndexService(campaign_name="test-campaign")

    with patch(
        "cocli.services.cluster_service.ClusterService.get_nodes",
        return_value=[PiNodeConfig(host="cocli5x1", ip="10.0.0.2")],
    ), patch("subprocess.run") as mock_run:
        mock_run.return_value = _fake_result("COCLI_ARCHIVE_RESULT archived=0 kept=0\n")
        result = service.archive_incomplete_schema_wal(required_field_count=56, dry_run=True)

    assert result.required_field_count == 56
    script = mock_run.call_args[1]["input"]
    assert "required = 56" in script
