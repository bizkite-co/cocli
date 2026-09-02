"""
Command-layer regression tests for `cocli cluster stop/sync-clocks/prune`.

These exist because the original bug (per-node progress prints orphaned from
the actual per-node action during the cluster.py business-logic extraction)
lived entirely in the Typer command wiring, not the service layer. A
service-only test (see tests/unit/test_cluster_service.py) cannot catch a
regression where the command layer stops passing log_callback through.
"""
from __future__ import annotations
from typing import Any, Callable, Optional
from unittest.mock import patch

from typer.testing import CliRunner

from cocli.core.paths import paths as real_paths

runner = CliRunner()


class FakeNode:
    def __init__(self, hostname: str) -> None:
        self.hostname = hostname


class FakeClusterService:
    def __init__(self, campaign_name: str) -> None:
        self.campaign_name = campaign_name

    def get_nodes(self) -> list[FakeNode]:
        return [FakeNode("fake-node")]

    async def stop_workers(self, log_callback: Optional[Callable[[str], None]] = None) -> None:
        if log_callback:
            log_callback("Stopping workers on fake-node...")

    async def sync_clocks(
        self,
        authoritative_node: str,
        auth_time: str,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        if log_callback:
            log_callback("Syncing fake-node...")

    async def prune_nodes(
        self,
        validated_nodes: list[Any],
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> list[dict]:
        if log_callback:
            log_callback("Pruning fake-node...")
        return [{"node": "fake-node", "success": True, "reclaimed": "1 GB"}]


def test_cluster_stop_prints_per_node_progress(cli_app):
    with patch("cocli.commands.cluster.ClusterService", FakeClusterService):
        result = runner.invoke(cli_app, ["cluster", "stop", "--campaign", "test-campaign"])

    assert result.exit_code == 0
    assert "Stopping workers on fake-node..." in result.stdout


def test_cluster_sync_clocks_prints_per_node_progress(cli_app):
    with patch("subprocess.run") as mock_subprocess_run, \
         patch("cocli.services.cluster_service.ClusterService", FakeClusterService):
        mock_subprocess_run.return_value.stdout = "2026-07-14 17:42:00"
        result = runner.invoke(cli_app, ["cluster", "sync-clocks"])

    assert result.exit_code == 0
    assert "Syncing fake-node..." in result.stdout


def test_cluster_prune_prints_per_node_progress(cli_app):
    fake_campaign_dir = real_paths.campaigns / "test-campaign"
    with patch("cocli.core.config.get_all_campaign_dirs", return_value=[fake_campaign_dir]), \
         patch("cocli.commands.cluster.ClusterService", FakeClusterService):
        result = runner.invoke(cli_app, ["cluster", "prune"])

    assert result.exit_code == 0
    assert "Pruning fake-node..." in result.stdout
