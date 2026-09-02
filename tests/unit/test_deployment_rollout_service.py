"""Unit tests for DeploymentService campaign rollout extraction."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import toml

from cocli.application.deployment_service import (
    BroadcastConfigResult,
    ConfigSyncResult,
    DeploymentService,
    RolloutDiagnostics,
    RolloutSyncResult,
)
from cocli.core.paths import paths


def test_count_lines_in_dir(tmp_path: Path) -> None:
    d = tmp_path / "active"
    d.mkdir()
    (d / "a.usv").write_text("1\n2\n3\n")
    (d / "b.usv").write_text("x\n")
    (d / "skip.txt").write_text("ignored\n")
    assert DeploymentService.count_lines_in_dir(d) == 4
    assert DeploymentService.count_lines_in_dir(tmp_path / "missing") == 0


def test_get_batch_status(tmp_path: Path) -> None:
    paths.root = tmp_path
    service = DeploymentService(campaign_name="road")
    # Create batches under discovery-gen pending
    batches_dir = (
        paths.campaign("road").queue("discovery-gen").pending / "batches"
    )
    batches_dir.mkdir(parents=True)
    (batches_dir / "canary.usv").write_text("a\nb\n")
    (batches_dir / "rollout_1.usv").write_text("x\n")

    status = service.get_batch_status("road")
    assert status.batches["canary"] == 2
    assert status.batches["rollout_1"] == 1
    assert status.total_tasks == 3


def test_get_rollout_diagnostics(tmp_path: Path) -> None:
    paths.root = tmp_path
    service = DeploymentService(campaign_name="road")
    batches_dir = (
        paths.campaign("road").queue("discovery-gen").pending / "batches"
    )
    batches_dir.mkdir(parents=True)
    (batches_dir / "canary.usv").write_text("a\nb\n")  # 2 tasks

    active = paths.campaign("road").index("google_maps_prospects").path / "active"
    active.mkdir(parents=True)
    (active / "shard.usv").write_text("p1\np2\np3\np4\n")  # 4 companies

    diag = service.get_rollout_diagnostics("road")
    assert isinstance(diag, RolloutDiagnostics)
    assert diag.total_tasks == 2
    assert diag.hub_companies == 4
    assert diag.avg_per_task == pytest.approx(2.0)
    assert diag.coverage_estimate_pct == pytest.approx(20.0)  # 4/(2*10)*100


def test_get_pi_stats_parses_ssh(monkeypatch: pytest.MonkeyPatch) -> None:
    service = DeploymentService(campaign_name="road")
    calls: list[str] = []

    def fake_ssh(hostname: str, command: str) -> tuple[int, str]:
        calls.append(hostname)
        if "wal" in command:
            return 0, "12"
        return 0, "7"

    monkeypatch.setattr(DeploymentService, "ssh_run", staticmethod(fake_ssh))
    stats = service.get_pi_stats("road")
    assert "cocli5x0" in stats
    assert stats["cocli5x0"].wal_companies == 12
    assert stats["cocli5x0"].active_companies == 7
    assert stats["cocli5x0"].reachable is True
    assert len(calls) >= 2


def test_broadcast_scaling_config_no_scaling(tmp_path: Path) -> None:
    paths.root = tmp_path
    camp = paths.campaign("road").path
    camp.mkdir(parents=True)
    (camp / "config.toml").write_text(toml.dumps({"prospecting": {}}))

    service = DeploymentService(campaign_name="road")
    result = service.broadcast_scaling_config("road")
    assert isinstance(result, BroadcastConfigResult)
    assert result.scaling == {}
    assert "No scaling" in result.message


def test_broadcast_scaling_config_sends(tmp_path: Path) -> None:
    paths.root = tmp_path
    camp = paths.campaign("road").path
    camp.mkdir(parents=True)
    (camp / "config.toml").write_text(
        toml.dumps({"prospecting": {"scaling": {"host-a": {"gm": 2}}}})
    )

    mock_bridge = MagicMock()
    steps: list[str] = []
    service = DeploymentService(campaign_name="road")

    with (
        patch("cocli.core.gossip_bridge.bridge", mock_bridge),
        patch("cocli.application.deployment_service.time.sleep"),
        patch(
            "cocli.core.environment.get_environment",
            return_value=MagicMock(value="DEV"),
        ),
    ):
        result = service.broadcast_scaling_config("road", log_callback=steps.append)

    assert result.success is True
    assert result.scaling == {"host-a": {"gm": 2}}
    assert any("Broadcasting scaling update" in s for s in steps)
    mock_bridge.start.assert_called_once()
    mock_bridge.broadcast_msg.assert_called_once()
    mock_bridge.stop.assert_called_once()


def test_push_config_to_s3(tmp_path: Path) -> None:
    paths.root = tmp_path
    camp = paths.campaign("road").path
    camp.mkdir(parents=True)
    (camp / "config.toml").write_text("[aws]\nprofile = 'p'\n")

    mock_s3 = MagicMock()
    service = DeploymentService(campaign_name="road")
    with (
        patch(
            "cocli.core.config.load_campaign_config",
            return_value={"aws": {"profile": "p"}},
        ),
        patch(
            "cocli.core.reporting.get_data_bucket_name", return_value="bucket"
        ),
        patch("cocli.core.reporting.get_boto3_session", return_value=MagicMock()),
        patch("cocli.core.reporting.get_s3_client", return_value=mock_s3),
    ):
        result = service.push_config_to_s3("road")

    assert isinstance(result, ConfigSyncResult)
    assert result.success is True
    assert "s3://bucket/" in result.message
    mock_s3.upload_file.assert_called_once()


def test_pull_config_from_s3_success(tmp_path: Path) -> None:
    paths.root = tmp_path
    camp = paths.campaign("road").path
    camp.mkdir(parents=True)
    (camp / "config.toml").write_text("[aws]\n")

    mock_s3 = MagicMock()
    service = DeploymentService(campaign_name="road")
    with (
        patch(
            "cocli.core.config.load_campaign_config",
            return_value={"aws": {}},
        ),
        patch(
            "cocli.core.reporting.get_data_bucket_name", return_value="bucket"
        ),
        patch("cocli.core.reporting.get_boto3_session", return_value=MagicMock()),
        patch("cocli.core.reporting.get_s3_client", return_value=mock_s3),
    ):
        result = service.pull_config_from_s3("road")

    assert result.success is True
    assert result.warning is False
    assert "Pulled s3://" in result.message
    mock_s3.download_file.assert_called_once()


def test_pull_config_from_s3_warning_on_failure(tmp_path: Path) -> None:
    paths.root = tmp_path
    camp = paths.campaign("road").path
    camp.mkdir(parents=True)
    (camp / "config.toml").write_text("[aws]\n")

    mock_s3 = MagicMock()
    mock_s3.download_file.side_effect = RuntimeError("NoSuchKey")
    service = DeploymentService(campaign_name="road")
    with (
        patch(
            "cocli.core.config.load_campaign_config",
            return_value={"aws": {}},
        ),
        patch(
            "cocli.core.reporting.get_data_bucket_name", return_value="bucket"
        ),
        patch("cocli.core.reporting.get_boto3_session", return_value=MagicMock()),
        patch("cocli.core.reporting.get_s3_client", return_value=mock_s3),
    ):
        result = service.pull_config_from_s3("road")

    assert result.success is True
    assert result.warning is True
    assert "Could not pull config" in result.message


def test_sync_rollout_results(tmp_path: Path) -> None:
    paths.root = tmp_path
    service = DeploymentService(campaign_name="road")

    batches_dir = (
        paths.campaign("road").queue("discovery-gen").pending / "batches"
    )
    batches_dir.mkdir(parents=True)
    (batches_dir / "canary.usv").write_text("t1\nt2\n")

    active = paths.campaign("road").index("google_maps_prospects").path / "active"
    active.mkdir(parents=True)
    # two unique place_ids; one duplicate
    (active / "a.usv").write_text("pid1\x1frest\npid2\x1frest\npid1\x1fagain\n")

    steps: list[str] = []
    with (
        patch(
            "cocli.core.config.load_campaign_config",
            return_value={"aws": {}},
        ),
        patch(
            "cocli.core.reporting.get_data_bucket_name", return_value="bucket"
        ),
        patch("cocli.core.smart_sync.run_smart_sync") as mock_sync,
    ):
        result = service.sync_rollout_results(
            "road", workers=5, log_callback=steps.append
        )

    assert isinstance(result, RolloutSyncResult)
    assert result.unique_companies == 2
    assert result.duplicates == 1
    assert result.total_tasks_deployed == 2
    assert result.avg_companies_per_task == pytest.approx(1.0)
    mock_sync.assert_called_once()
    assert any("Step 1/3" in s for s in steps)
    assert any("Step 2/3" in s for s in steps)
    assert any("Step 3/3" in s for s in steps)
