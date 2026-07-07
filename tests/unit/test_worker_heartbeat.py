import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cocli.application.worker_service import WorkerService
from cocli.core.logging_config import RollingErrorCounter, get_recent_error_count


@pytest.fixture
def mock_s3() -> MagicMock:
    return MagicMock()


def _make_child(content_type: str, worker_count: int, last_activity_ts: float) -> WorkerService:
    child = WorkerService.__new__(WorkerService)
    child.content_type = content_type
    child.worker_count = worker_count
    child.last_activity_ts = last_activity_ts
    return child


@pytest.mark.asyncio
async def test_heartbeat_reports_real_designation_from_child_workers(tmp_path: Path, mock_s3: MagicMock) -> None:
    with patch("cocli.core.paths.paths.root", tmp_path):
        supervisor = WorkerService(campaign_name="test_campaign", processed_by="node1")
        supervisor.child_workers = [
            _make_child("gm-details", 2, 100.0),
            _make_child("enrichment", 4, 200.0),
        ]

        with patch("psutil.cpu_percent", return_value=12.3), patch(
            "psutil.virtual_memory", return_value=MagicMock(percent=45.6)
        ):
            await supervisor._push_supervisor_heartbeat(mock_s3)

        assert mock_s3.put_object.called
        body = json.loads(mock_s3.put_object.call_args.kwargs["Body"])

        # Previously this was always {"s": 0, "d": 0, "e": 0} regardless of what
        # was actually running - the whole reason the heartbeat couldn't be
        # trusted as a signal source.
        assert body["workers"] == {"s": 0, "d": 2, "e": 4}
        assert body["designation"] == {"gm-details": 2, "enrichment": 4}
        assert "gm-details" in body["last_activity"]
        assert "enrichment" in body["last_activity"]
        assert body["error_count_30m"] == 0


def test_rolling_error_counter_ages_out_old_entries() -> None:
    counter = RollingErrorCounter()
    now = [1_000_000.0]

    with patch("cocli.core.logging_config.time.time", side_effect=lambda: now[0]):
        record = MagicMock()
        counter.emit(record)
        assert counter.count_since(60) == 1

        now[0] += 120  # advance past the 60s window
        assert counter.count_since(60) == 0


def test_get_recent_error_count_reflects_active_counter() -> None:
    from cocli.core import logging_config

    counter = RollingErrorCounter()
    logging_config._error_counter = counter
    counter.emit(MagicMock())
    counter.emit(MagicMock())

    assert get_recent_error_count(1800) == 2


@pytest.mark.asyncio
async def test_run_orchestrated_workers_survives_rebalance_mid_flight(tmp_path: Path) -> None:
    """
    Regression test for a real production crash-loop (turboship/cocli5x0,
    2026-07-07): _rebalance_workers() cancels the tasks in self.worker_tasks
    and replaces the list wholesale with new ones. run_orchestrated_workers
    used to await a fixed snapshot of the *original* tasks
    (`asyncio.gather(*self.worker_tasks)`, no return_exceptions) - once
    rebalance cancelled them, gather raised CancelledError and killed the
    whole orchestrator on every hot-reload from gossip.
    """
    with patch("cocli.core.paths.paths.root", tmp_path):
        supervisor = WorkerService(campaign_name="test_campaign", processed_by="node1")

    async def fake_run_worker(self: WorkerService, *args: object, **kwargs: object) -> None:
        await asyncio.sleep(100)

    wd = SimpleNamespace(name="n-gm-list", role="full", content_type="gm-list", workers=1)

    with patch.object(WorkerService, "run_worker", fake_run_worker), patch.object(
        supervisor, "_watch_remote_config", new=AsyncMock()
    ), patch.object(supervisor, "_heartbeat_loop", new=AsyncMock()), patch(
        "cocli.core.gossip_bridge.bridge", None
    ):
        orchestrator_task = asyncio.create_task(
            supervisor.run_orchestrated_workers([wd], headless=True, debug=False)
        )
        await asyncio.sleep(0.05)  # let it create the initial task(s)

        # Simulate exactly what _rebalance_workers() does: cancel the
        # current tasks, wait them out, then swap in a fresh list.
        old_tasks = supervisor.worker_tasks
        for t in old_tasks:
            t.cancel()
        await asyncio.gather(*old_tasks, return_exceptions=True)
        supervisor.worker_tasks = [asyncio.create_task(asyncio.sleep(100))]

        # The critical assertion: a fixed rebalance-mid-flight bug used to
        # let run_orchestrated_workers return right here (either by
        # crashing on CancelledError, or - a subtler regression caught
        # while fixing the first bug - by racing _rebalance_workers()'s own
        # reassignment and deciding "no rebalance happened, exit" before
        # the new task list was actually in place). It must still be
        # running, awaiting the replacement tasks.
        await asyncio.sleep(0.2)
        assert not orchestrator_task.done(), (
            "run_orchestrated_workers returned after a rebalance instead of "
            "picking up the replacement worker_tasks"
        )

        supervisor._running = False
        for t in supervisor.worker_tasks:
            t.cancel()
        await asyncio.wait_for(orchestrator_task, timeout=5)


@pytest.mark.asyncio
async def test_rebalance_workers_registers_child_workers(tmp_path: Path) -> None:
    """
    Regression test for a real production incident (2026-07-07): audit
    designation showed only "gm-list: 2" for a node that was actually also
    running gm-details (invisible to monitoring), and reported a false
    STALE verdict for gm-list despite it completing tasks every 1-5
    minutes. Root cause: _rebalance_workers() replaced the running workers
    by calling the run coroutine directly on `self` instead of a dedicated
    child WorkerService registered in self.child_workers - the only thing
    _push_supervisor_heartbeat's designation/last-activity aggregation
    reads. Fixed to mirror run_orchestrated_workers()'s existing pattern.
    """
    fake_config = {
        "prospecting": {
            "scaling": {
                "testnode": {"gm-list": 1, "gm-details": 1, "enrichment": 0}
            }
        },
        "aws": {"iot_profiles": ["test-iot"]},
    }

    with patch("cocli.core.paths.paths.root", tmp_path), patch(
        "cocli.application.worker_service.load_campaign_config", return_value=fake_config
    ):
        supervisor = WorkerService(campaign_name="test_campaign", processed_by="testnode")

    async def fake_run_worker(self: WorkerService, *args: object, **kwargs: object) -> None:
        await asyncio.sleep(100)

    async def fake_run_details_worker(self: WorkerService, *args: object, **kwargs: object) -> None:
        await asyncio.sleep(100)

    with patch("cocli.application.worker_service.load_campaign_config", return_value=fake_config), patch.object(
        WorkerService, "run_worker", fake_run_worker
    ), patch.object(WorkerService, "run_details_worker", fake_run_details_worker):
        await supervisor._rebalance_workers()

        assert len(supervisor.child_workers) == 2, (
            "expected one child WorkerService per non-zero content type "
            f"(gm-list, gm-details), got {len(supervisor.child_workers)}"
        )
        content_types = {w.content_type for w in supervisor.child_workers}
        assert content_types == {"gm-list", "gm-details"}
        assert len(supervisor.worker_tasks) == 2

        for t in supervisor.worker_tasks:
            t.cancel()
        await asyncio.gather(*supervisor.worker_tasks, return_exceptions=True)
