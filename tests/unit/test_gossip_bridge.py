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


def test_listen_loop_sets_suppression_flag_before_processing() -> None:
    bridge, mock_sock = _make_bridge()
    bridge.running = True

    def stop_after_one_iteration(*args: object, **kwargs: object) -> None:
        bridge.running = False
        raise socket.timeout()

    mock_sock.recvfrom.side_effect = stop_after_one_iteration

    bridge._listen_loop()

    assert bridge._suppress_broadcast.active is True
