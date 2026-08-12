"""WorkerService._watch_remote_config(): gossip-pushed scaling broadcasts must
not be replayed forever and must never cross a campaign boundary.

Split out of task-agent ticket
turboship-gm-details-worker-silently-dies-every-restart-never-polls. That
incident's proximate cause was a stuck gm-details=0 broadcast, but the
underlying bug is general: an in-memory `last_processed` watermark reset to
0 on every container restart while the on-disk broadcast files it tracked
against (bind-mounted, so restart-durable) were never deleted. Live
inspection (2026-08-12) found 9 such files on cocli5x0 dating back to
2026-07-05, none ever processed away - proof this has been silently
replaying stale config on every restart for over a month.

See task-agent ticket
gossip-config-broadcasts-never-expire-stale-scaling-replayed-forever-no-cross-campaign-guard.
"""

import json

import pytest
import toml

from cocli.application.worker_service import WorkerService
from cocli.core.paths import paths


def _make_service(tmp_path, campaign_name: str = "test-campaign", processed_by: str = "testnode") -> WorkerService:
    paths.root = tmp_path
    campaign_dir = tmp_path / "campaigns" / campaign_name
    campaign_dir.mkdir(parents=True)
    with open(campaign_dir / "config.toml", "w") as f:
        toml.dump({"prospecting": {"scaling": {"testnode": {"gm-list": 1}}}}, f)
    return WorkerService(campaign_name=campaign_name, processed_by=processed_by)


def _write_update(update_dir, ts: int, campaign_name: str, scaling: dict) -> None:
    update_dir.mkdir(parents=True, exist_ok=True)
    (update_dir / f"config_{ts}.json").write_text(
        json.dumps({"campaign_name": campaign_name, "scaling": scaling})
    )


async def _stop_after_one_iteration(service: WorkerService, seconds: float) -> None:
    service._running = False


@pytest.mark.asyncio
async def test_deletes_processed_file_after_apply(tmp_path, monkeypatch):
    service = _make_service(tmp_path)
    service._running = True
    update_dir = tmp_path / "remote_updates"
    _write_update(update_dir, 1000, "test-campaign", {"testnode": {"gm-list": 2}})

    async def fake_rebalance() -> None:
        return None

    monkeypatch.setattr(service, "_rebalance_workers", fake_rebalance)
    monkeypatch.setattr("asyncio.sleep", lambda s: _stop_after_one_iteration(service, s))

    await service._watch_remote_config()

    assert list(update_dir.glob("config_*.json")) == []


@pytest.mark.asyncio
async def test_second_restart_does_not_replay_a_file_already_deleted(tmp_path, monkeypatch):
    # Simulates the exact incident: _watch_remote_config() is a fresh
    # coroutine call each time (as it is on every container restart), so
    # nothing in-memory can protect against reprocessing - only the file
    # actually being gone can.
    service = _make_service(tmp_path)
    update_dir = tmp_path / "remote_updates"
    _write_update(update_dir, 1000, "test-campaign", {"testnode": {"gm-list": 2}})

    calls = []

    async def fake_rebalance() -> None:
        calls.append(1)

    monkeypatch.setattr(service, "_rebalance_workers", fake_rebalance)
    monkeypatch.setattr("asyncio.sleep", lambda s: _stop_after_one_iteration(service, s))

    service._running = True
    await service._watch_remote_config()
    assert len(calls) == 1

    # Second "restart": brand new call, no shared state with the first.
    service._running = True
    await service._watch_remote_config()
    assert len(calls) == 1  # unchanged - nothing left to replay


@pytest.mark.asyncio
async def test_merges_only_this_nodes_own_hostname_slice(tmp_path, monkeypatch):
    service = _make_service(tmp_path)
    service._running = True
    update_dir = tmp_path / "remote_updates"
    _write_update(
        update_dir,
        1000,
        "test-campaign",
        {"testnode": {"gm-list": 5}, "othernode": {"gm-list": 99}, "fargate": {"enrichment": 3}},
    )

    async def fake_rebalance() -> None:
        return None

    monkeypatch.setattr(service, "_rebalance_workers", fake_rebalance)
    monkeypatch.setattr("asyncio.sleep", lambda s: _stop_after_one_iteration(service, s))

    await service._watch_remote_config()

    config_path = tmp_path / "campaigns" / "test-campaign" / "config.toml"
    scaling = toml.load(config_path)["prospecting"]["scaling"]
    assert scaling["testnode"] == {"gm-list": 5}
    assert "othernode" not in scaling
    assert "fargate" not in scaling


@pytest.mark.asyncio
async def test_rejects_cross_campaign_broadcast(tmp_path, monkeypatch, caplog):
    # The latent risk found live: a node reassigned between campaigns can
    # still have an old broadcast file from its prior campaign sitting on
    # the same bind-mounted data directory.
    service = _make_service(tmp_path, campaign_name="test-campaign")
    service._running = True
    update_dir = tmp_path / "remote_updates"
    _write_update(update_dir, 1000, "some-other-campaign", {"testnode": {"gm-list": 99}})

    async def fake_rebalance() -> None:
        raise AssertionError("must not rebalance on a cross-campaign broadcast")

    monkeypatch.setattr(service, "_rebalance_workers", fake_rebalance)
    monkeypatch.setattr("asyncio.sleep", lambda s: _stop_after_one_iteration(service, s))

    with caplog.at_level("WARNING", logger="cocli.application.worker_service"):
        await service._watch_remote_config()

    config_path = tmp_path / "campaigns" / "test-campaign" / "config.toml"
    scaling = toml.load(config_path)["prospecting"]["scaling"]
    assert scaling["testnode"] == {"gm-list": 1}  # untouched
    assert "some-other-campaign" in caplog.text
    assert list(update_dir.glob("config_*.json")) == []  # still cleaned up, not left to retry


@pytest.mark.asyncio
async def test_rejects_legacy_format_without_campaign_tag(tmp_path, monkeypatch, caplog):
    # Pre-fix broadcast files (raw scaling dict, no wrapper) carry no
    # campaign identity - there's no way to verify they're safe to apply,
    # so drop them rather than risk a silent cross-campaign replay.
    service = _make_service(tmp_path)
    service._running = True
    update_dir = tmp_path / "remote_updates"
    update_dir.mkdir(parents=True)
    (update_dir / "config_1000.json").write_text(json.dumps({"testnode": {"gm-list": 99}}))

    async def fake_rebalance() -> None:
        raise AssertionError("must not rebalance on a legacy untagged broadcast")

    monkeypatch.setattr(service, "_rebalance_workers", fake_rebalance)
    monkeypatch.setattr("asyncio.sleep", lambda s: _stop_after_one_iteration(service, s))

    with caplog.at_level("WARNING", logger="cocli.application.worker_service"):
        await service._watch_remote_config()

    config_path = tmp_path / "campaigns" / "test-campaign" / "config.toml"
    scaling = toml.load(config_path)["prospecting"]["scaling"]
    assert scaling["testnode"] == {"gm-list": 1}  # untouched
    assert "legacy format" in caplog.text.lower()
    assert list(update_dir.glob("config_*.json")) == []
