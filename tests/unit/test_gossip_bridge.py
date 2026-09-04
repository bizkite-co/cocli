import importlib
import json
import socket
import threading
import time
from unittest.mock import MagicMock

from cocli.core import gossip_bridge as _gossip_bridge_module
from cocli.core.environment import Environment
from cocli.core.paths import paths
from cocli.models.wal.record import ConfigDatagram

# tests/conftest.py globally replaces cocli.core.gossip_bridge.GossipBridge
# with a MagicMock for the whole test session, to stop any test from
# accidentally starting real gossip/zeroconf threads. These tests need the
# *real* class to verify the actual broadcast-suppression logic, so reload
# once to get it back as a local reference (this module's own GossipBridge
# name), then immediately re-apply conftest.py's same patches so test
# modules that run later in the same session still get the mocked version.
importlib.reload(_gossip_bridge_module)
GossipBridge = _gossip_bridge_module.GossipBridge

from unittest.mock import patch as _module_patch  # noqa: E402

_mock_bridge = MagicMock()
_mock_bridge.heartbeats = {}
_module_patch("cocli.core.gossip_bridge.bridge", _mock_bridge).start()
_module_patch("cocli.core.gossip_bridge.GossipBridge", MagicMock()).start()
_module_patch("cocli.core.gossip_bridge.GossipBridge.start", lambda x: None).start()
_module_patch("cocli.core.gossip_bridge.GossipBridge.stop", lambda x: None).start()
_module_patch("cocli.core.gossip_bridge.Zeroconf", MagicMock()).start()
_module_patch("cocli.core.gossip_bridge.ServiceBrowser", MagicMock()).start()


def _make_bridge() -> tuple[_gossip_bridge_module.GossipBridge, MagicMock]:
    # __new__ skips __init__, so none of __init__'s paths/config setup runs -
    # safe here since these tests only exercise broadcast_msg/_listen_loop.
    bridge = GossipBridge.__new__(GossipBridge)
    bridge.peers = {"peer-1": "10.0.0.99"}
    mock_sock = MagicMock(spec=socket.socket)
    bridge.sock = mock_sock
    bridge._suppress_broadcast = threading.local()
    return bridge, mock_sock


def test_broadcast_msg_sends_when_not_suppressed() -> None:
    bridge, mock_sock = _make_bridge()

    bridge.broadcast_msg("Qsomepayload")

    assert mock_sock.sendto.called


def test_broadcast_msg_suppressed_on_listener_thread() -> None:
    """
    Regression test for a real production incident (turboship/cocli5x0 <->
    roadmap/cocli5x1, 2026-07-07): applying an incoming "Q" gossip sync via
    q_manager.ack()/nack() unconditionally re-broadcasts as a side effect
    (correct for a genuine local task completion). With no suppression,
    receiving a sync -> applying it -> re-broadcasting -> the peer receiving
    that -> re-applying -> re-broadcasting back created an unthrottled
    ping-pong measured at 300+ msg/s and ~330% CPU on both nodes.
    """
    bridge, mock_sock = _make_bridge()
    bridge._suppress_broadcast.active = True

    bridge.broadcast_msg("Qsomepayload")

    assert not mock_sock.sendto.called


def test_handle_gossip_config_writes_campaign_tagged_payload(tmp_path, monkeypatch) -> None:
    """Regression lock for the general-purpose fix in task-agent ticket
    gossip-config-broadcasts-never-expire-stale-scaling-replayed-forever-no-cross-campaign-guard:
    the write side must tag every broadcast file with its campaign_name so
    the reader (WorkerService._watch_remote_config) can independently
    verify it before ever applying it, instead of trusting the write-side
    filter to hold forever across node reassignments."""
    bridge, _mock_sock = _make_bridge()
    bridge.node_id = "self-node"
    paths.root = tmp_path
    monkeypatch.setenv("CAMPAIGN_NAME", "test-campaign")
    monkeypatch.setattr(_gossip_bridge_module, "get_environment", lambda: Environment.DEV)

    datagram = ConfigDatagram(
        campaign_name="test-campaign",
        node_id="*",
        timestamp=str(int(time.time())),
        config_json=json.dumps({"testnode": {"gm-list": 2}}),
        environment="dev",
    )

    bridge.handle_gossip(datagram.to_usv(), ("10.0.0.5", 1234))

    files = list((tmp_path / "remote_updates").glob("config_*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text()) == {
        "campaign_name": "test-campaign",
        "scaling": {"testnode": {"gm-list": 2}},
    }


def test_handle_gossip_does_not_auto_learn_rfc1918_senders() -> None:
    """10.0.0.0/16 is both the house LAN and AWS VPC. Auto-learning any
    10.0.0.* sender permanently filled peers with Fargate leftovers."""
    bridge, _mock_sock = _make_bridge()
    bridge.node_id = "cocli5x0"
    bridge._peer_allowlist = {"cocli5x1"}
    monkey_env = _gossip_bridge_module.get_environment
    _gossip_bridge_module.get_environment = lambda: Environment.DEV
    try:
        bridge.handle_gossip("not-a-valid-datagram", ("10.0.0.194", 9998))
    finally:
        _gossip_bridge_module.get_environment = monkey_env
    assert "discovered_194" not in bridge.peers
    assert bridge.peers == {"peer-1": "10.0.0.99"}


def test_registry_entry_skips_expired_and_legacy_fargate() -> None:
    now = 1_000_000.0
    allow = {"cocli5x1"}
    assert not _gossip_bridge_module.registry_entry_is_live(
        "ip-10-0-1-77.ec2.internal",
        "10.0.1.77",
        {"ip": "10.0.1.77", "timestamp": now - 86400},
        now=now,
        allowlist=allow,
    )
    assert _gossip_bridge_module.registry_entry_is_live(
        "ip-10-0-1-77.ec2.internal",
        "10.0.1.77",
        {"ip": "10.0.1.77", "expires_at": now + 60},
        now=now,
        allowlist=allow,
    )
    assert not _gossip_bridge_module.registry_entry_is_live(
        "ip-10-0-1-77.ec2.internal",
        "10.0.1.77",
        {"ip": "10.0.1.77", "expires_at": now - 1},
        now=now,
        allowlist=allow,
    )
    assert _gossip_bridge_module.registry_entry_is_live(
        "cocli5x1",
        "10.0.0.17",
        {"ip": "10.0.0.17", "timestamp": now - 60},
        now=now,
        allowlist=allow,
    )
    assert not _gossip_bridge_module.registry_entry_is_live(
        "ab29a6cf6e98",
        "172.17.0.2",
        {"ip": "172.17.0.2", "expires_at": now + 60},
        now=now,
        allowlist=allow,
    )


def test_campaign_peer_allowlist_excludes_fargate_and_self() -> None:
    config = {
        "cluster": {
            "registry_host": "cocli5x0",
            "nodes": [{"host": "cocli5x0"}, {"hostname": "cocli5x1"}],
        },
        "prospecting": {"scaling": {"cocli5x0": {}, "fargate": {}, "laptop": {}}},
    }
    names = _gossip_bridge_module.campaign_peer_allowlist(config, "cocli5x0")
    assert "cocli5x1" in names
    assert "laptop" in names
    assert "fargate" not in names
    assert "cocli5x0" not in names


def test_broadcast_msg_drops_peer_after_consecutive_send_failures() -> None:
    bridge, mock_sock = _make_bridge()
    bridge.peers = {"dead": "10.0.1.77", "live": "10.0.0.17"}
    bridge._send_failures = {}
    mock_sock.sendto.side_effect = [
        OSError("timed out"),
        None,
        OSError("timed out"),
        None,
        OSError("timed out"),
        None,
    ]

    bridge.broadcast_msg("Q1")
    bridge.broadcast_msg("Q2")
    assert "dead" in bridge.peers
    bridge.broadcast_msg("Q3")
    assert "dead" not in bridge.peers
    assert bridge.peers == {"live": "10.0.0.17"}


def test_listen_loop_sets_suppression_flag_before_processing() -> None:
    bridge, mock_sock = _make_bridge()
    bridge.running = True

    def stop_after_one_iteration(*args: object, **kwargs: object) -> None:
        bridge.running = False
        raise socket.timeout()

    mock_sock.recvfrom.side_effect = stop_after_one_iteration

    bridge._listen_loop()

    assert bridge._suppress_broadcast.active is True
