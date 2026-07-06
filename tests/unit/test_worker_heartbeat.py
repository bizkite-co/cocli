import json
from pathlib import Path
from unittest.mock import MagicMock, patch

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
