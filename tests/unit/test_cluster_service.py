import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from cocli.services.cluster_service import ClusterService, find_node_ownership_conflicts
from cocli.models.campaigns.worker_config import PiNodeConfig


@pytest.mark.asyncio
async def test_cluster_service_stats_and_status(monkeypatch):
    service = ClusterService("roadmap")
    
    # Mock run_remote_command
    async def mock_run_remote_command(node, cmd, user="mstouffer"):
        if "uptime" in cmd and "vcgencmd" in cmd:
            return " 17:42:00 up 10 days, 1:23, load average: 0.12, 0.08, 0.05\ntemp=45.2'C\n2.5 GB / 4.0 GB | 12\n"
        elif "uptime" in cmd:
            return " 17:42:00 up 10 days, 1:23, load average: 0.12\n"
        elif "docker system prune" in cmd:
            return "Deleted Containers: ...\nTotal reclaimed space: 1.25 GB\n"
        return ""

    monkeypatch.setattr(service, "run_remote_command", mock_run_remote_command)
    
    # Setup mock nodes
    node1 = PiNodeConfig(host="node1", ip=None, workers=[])
    monkeypatch.setattr(service, "get_nodes", lambda: [node1])

    # Test top stats
    stats = await service.get_top_stats()
    assert len(stats) == 1
    assert stats[0]["node"] == "node1"
    assert stats[0]["load"] == "0.12, 0.08, 0.05"
    assert stats[0]["temp"] == "45.2'C"
    assert stats[0]["mem"] == "2.5 GB / 4.0 GB"
    assert stats[0]["pids"] == "12"

    # Test clock sync
    await service.sync_clocks("authority", "2026-07-14 17:42:00")

    # Test stop workers
    await service.stop_workers()

    # Test nodes status
    status = await service.get_nodes_status()
    assert len(status) == 1
    assert status[0]["node"] == "node1"
    assert status[0]["online"] is True
    assert status[0]["uptime"] == "10 days"

    # Test prune nodes
    prune_res = await service.prune_nodes([node1])
    assert len(prune_res) == 1
    assert prune_res[0]["node"] == "node1"
    assert prune_res[0]["success"] is True
    assert prune_res[0]["reclaimed"] == "1.25 GB"


@pytest.mark.asyncio
async def test_get_nodes_status_reports_live_container_campaign(monkeypatch):
    """get_nodes_status() must report the CAMPAIGN_NAME actually baked into
    the node's running container - the ground truth of what it's serving
    right now - not just echo back whichever campaign's config.toml we
    queried it through. Confirmed drift incident 2026-08-07: a node's live
    campaign can differ from what its config file says (see
    reference_cluster_config_propagation memory)."""
    service = ClusterService("turboship")

    async def mock_run_remote_command(node, cmd, user="mstouffer"):
        assert "CAMPAIGN_NAME" in cmd
        if node.hostname == "cocli5x0":
            return " 17:42:00 up 10 days, load average: 0.12\n---CAMPAIGN---\nturboship\n"
        # cocli5x1: no cocli-supervisor container running at all - the
        # docker inspect/grep/cut pipeline produces empty output.
        return " 17:42:00 up 2 days, load average: 0.01\n---CAMPAIGN---\n"

    monkeypatch.setattr(service, "run_remote_command", mock_run_remote_command)
    monkeypatch.setattr(
        service,
        "get_nodes",
        lambda: [
            PiNodeConfig(host="cocli5x0", ip=None, workers=[]),
            PiNodeConfig(host="cocli5x1", ip=None, workers=[]),
        ],
    )

    status = await service.get_nodes_status()
    assert len(status) == 2
    by_node = {s["node"]: s for s in status}
    assert by_node["cocli5x0"]["campaign"] == "turboship"
    assert by_node["cocli5x1"]["campaign"] == "none running"


def _write_campaign_cluster_config(campaigns_root: Path, campaign_name: str, hostnames: list[str]) -> None:
    campaign_dir = campaigns_root / campaign_name
    campaign_dir.mkdir(parents=True)
    lines = ["[cluster]", f'registry_host = "{hostnames[0]}"']
    for hostname in hostnames:
        lines.append("[[cluster.nodes]]")
        lines.append(f'hostname = "{hostname}"')
        lines.append("[[cluster.nodes.workers]]")
        lines.append('name = "w1"')
        lines.append('role = "full"')
        lines.append('content_type = "gm-list"')
        lines.append("workers = 1")
    (campaign_dir / "config.toml").write_text("\n".join(lines) + "\n")


def test_find_node_ownership_conflicts_detects_shared_hostname(tmp_path: Path) -> None:
    """No separate ownership registry - conflicts are derived purely from
    each campaign's own [cluster.nodes], so there's nothing extra to keep in
    sync. Confirmed real incident 2026-08-07: roadmap's config.toml still
    declared cocli5x0 after it was reassigned to serve turboship only."""
    campaigns_root = tmp_path / "campaigns"
    _write_campaign_cluster_config(campaigns_root, "turboship", ["cocli5x0"])
    _write_campaign_cluster_config(campaigns_root, "roadmap", ["cocli5x0", "cocli5x1"])

    with patch("cocli.core.paths.paths.root", tmp_path):
        conflicts = find_node_ownership_conflicts()

    assert set(conflicts.keys()) == {"cocli5x0"}
    assert sorted(conflicts["cocli5x0"]) == ["roadmap", "turboship"]


def test_find_node_ownership_conflicts_none_when_disjoint(tmp_path: Path) -> None:
    campaigns_root = tmp_path / "campaigns"
    _write_campaign_cluster_config(campaigns_root, "turboship", ["cocli5x0"])
    _write_campaign_cluster_config(campaigns_root, "roadmap", ["cocli5x1"])

    with patch("cocli.core.paths.paths.root", tmp_path):
        conflicts = find_node_ownership_conflicts()

    assert conflicts == {}


@pytest.mark.asyncio
async def test_deploy_hotfix_safe_blocks_on_ownership_conflict() -> None:
    """The dangerous action is the deploy itself - it restarts the node
    under this campaign's worker mix, which is how a contested node gets
    silently stolen from whoever it's actually serving. Must refuse before
    touching the network, not just warn."""
    service = ClusterService.__new__(ClusterService)
    service.campaign_name = "turboship"
    service.config = {}
    service.registry_host = "cocli5x0"
    service.registry_url = "100.125.159.65:5000"
    service.get_nodes = lambda: [PiNodeConfig(host="cocli5x0", ip=None, workers=[])]  # type: ignore[method-assign]

    with patch.object(ClusterService, "_verify_local_build", return_value=True), \
        patch.object(ClusterService, "_sync_and_build", new_callable=AsyncMock) as mock_sync_and_build, \
        patch(
            "cocli.services.cluster_service.find_node_ownership_conflicts",
            return_value={"cocli5x0": ["turboship", "roadmap"]},
        ):
        results = await service.deploy_hotfix_safe()

    assert results == {"cocli5x0": False}
    mock_sync_and_build.assert_not_called()


@pytest.mark.asyncio
async def test_deploy_hotfix_safe_force_bypasses_ownership_conflict() -> None:
    service = ClusterService.__new__(ClusterService)
    service.campaign_name = "turboship"
    service.config = {}
    service.registry_host = "cocli5x0"
    service.registry_url = "100.125.159.65:5000"
    service.get_nodes = lambda: [PiNodeConfig(host="cocli5x0", ip=None, workers=[])]  # type: ignore[method-assign]

    with patch.object(ClusterService, "_verify_local_build", return_value=True), \
        patch.object(ClusterService, "_sync_and_build", new_callable=AsyncMock, return_value=True), \
        patch(
            "cocli.services.cluster_service.find_node_ownership_conflicts",
            return_value={"cocli5x0": ["turboship", "roadmap"]},
        ) as mock_conflicts:
        results = await service.deploy_hotfix_safe(force=True)

    assert results == {"cocli5x0": True}
    mock_conflicts.assert_not_called()


@pytest.mark.asyncio
async def test_cluster_service_log_callback_fires_per_node(monkeypatch):
    """
    Regression test: sync_clocks/stop_workers/prune_nodes must invoke
    log_callback once per node, interleaved with that node's own remote
    command - not all upfront before any work happens. This is the gap that
    let the command-layer progress prints get orphaned from the actual
    per-node action during the cluster.py extraction.
    """
    service = ClusterService("roadmap")

    async def mock_run_remote_command(node, cmd, user="mstouffer"):
        if "docker system prune" in cmd:
            return "Total reclaimed space: 1.25 GB\n"
        return ""

    monkeypatch.setattr(service, "run_remote_command", mock_run_remote_command)

    node1 = PiNodeConfig(host="node1", ip=None, workers=[])
    node2 = PiNodeConfig(host="node2", ip=None, workers=[])
    monkeypatch.setattr(service, "get_nodes", lambda: [node1, node2])

    messages = []

    def log_cb(msg: str) -> None:
        messages.append(msg)

    await service.sync_clocks("node1", "2026-07-14 17:42:00", log_callback=log_cb)
    assert messages == ["Syncing node2..."]

    messages.clear()
    await service.stop_workers(log_callback=log_cb)
    assert messages == ["Stopping workers on node1...", "Stopping workers on node2..."]

    messages.clear()
    await service.prune_nodes([node1, node2], log_callback=log_cb)
    assert messages == ["Pruning node1...", "Pruning node2..."]


@pytest.mark.asyncio
async def test_run_remote_command_does_not_block_event_loop() -> None:
    """Regression pin: run_remote_command used to shell out via blocking
    subprocess.run() inside an async def, so asyncio.gather()-ing it across
    N nodes still ran N SSH round-trips back-to-back - gather() can't
    parallelize a call that never yields control back to the loop. Confirmed
    by timing 3 concurrent calls against a fake subprocess that sleeps: if
    still serialized, this takes ~3x the per-call sleep instead of ~1x."""
    service = ClusterService.__new__(ClusterService)
    service.campaign_name = "roadmap"

    class FakeProc:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            await asyncio.sleep(0.2)
            return b"ok", b""

    async def fake_create_subprocess_exec(*args: object, **kwargs: object) -> FakeProc:
        return FakeProc()

    nodes = [PiNodeConfig(host=f"node{i}", ip=None, workers=[]) for i in range(3)]

    with patch("asyncio.create_subprocess_exec", side_effect=fake_create_subprocess_exec):
        start = time.monotonic()
        results = await asyncio.gather(
            *(service.run_remote_command(n, "echo hi") for n in nodes)
        )
        elapsed = time.monotonic() - start

    assert results == ["ok", "ok", "ok"]
    # 3 sequential 0.2s calls would take >=0.6s; concurrent execution stays
    # close to a single call's duration.
    assert elapsed < 0.5, f"expected concurrent execution, took {elapsed:.2f}s"
