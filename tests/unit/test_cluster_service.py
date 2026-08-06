import pytest
from cocli.services.cluster_service import ClusterService
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
