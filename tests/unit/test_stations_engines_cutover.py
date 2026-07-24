"""Phase 3: cocli cutovers driven by stations TransformEngine / Compactor."""

from __future__ import annotations

import json
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, List

from cocli.core.email_index_manager import EmailIndexManager
from cocli.core.stations_runtime import (
    compact_email_index_stations_only,
    run_queue_transform_once,
)
from cocli.models.campaigns.indexes.email import EmailEntry


class _FakeTask:
    def __init__(self, task_id: str, n: int = 1) -> None:
        self.task_id = task_id
        self.n = n


class _FakeQueue:
    campaign_name = "test-campaign"
    queue_name = "to-call"

    def __init__(self) -> None:
        self._items: List[_FakeTask] = []
        self.acked: List[_FakeTask] = []
        self.nacked: List[_FakeTask] = []

    def push(self, task: _FakeTask) -> Any:
        self._items.append(task)
        return task.task_id

    def poll(self, batch_size: int = 1) -> List[_FakeTask]:
        out = self._items[:batch_size]
        self._items = self._items[batch_size:]
        return out

    def ack(self, task: _FakeTask) -> None:
        self.acked.append(task)

    def nack(self, task: _FakeTask, is_http_500: bool = False) -> None:
        _ = is_http_500
        self.nacked.append(task)


def test_queue_transform_once_uses_stations_engine() -> None:
    q = _FakeQueue()
    q.push(_FakeTask("t1", 2))
    outputs: List[Any] = []

    def double(task: _FakeTask) -> dict[str, Any]:
        return {"task_id": task.task_id, "n": task.n * 2}

    assert (
        run_queue_transform_once(
            q,
            double,
            worker_id="test-worker",
            on_output=outputs.append,
            model=_FakeTask,
        )
        is True
    )
    assert len(q.acked) == 1
    assert q.acked[0].task_id == "t1"
    assert outputs == [{"task_id": "t1", "n": 4}]
    # idle when empty
    assert (
        run_queue_transform_once(
            q, double, worker_id="test-worker", model=_FakeTask
        )
        is False
    )


def test_email_index_stations_compactor_writes_current(
    tmp_path: Path, monkeypatch: Any
) -> None:
    campaign = "email-cutover"
    # Point campaign dir at tmp
    camp_dir = tmp_path / "campaigns" / campaign
    camp_dir.mkdir(parents=True)

    monkeypatch.setattr(
        "cocli.core.email_index_manager.get_campaign_dir",
        lambda _name: camp_dir,
    )

    mgr = EmailIndexManager(campaign)
    # Write inbox as JSON records stations PathLogEdge can deserialize
    inbox = mgr.inbox_dir / "aa"
    inbox.mkdir(parents=True)
    e1 = EmailEntry(
        email="a@example.com",
        domain="example.com",
        source="test",
        last_seen=datetime(2026, 1, 2, tzinfo=UTC),
    )
    e2 = EmailEntry(
        email="a@example.com",
        domain="example.com",
        source="test",
        last_seen=datetime(2026, 1, 3, tzinfo=UTC),
    )
    (inbox / "a@example.com.json").write_text(e1.model_dump_json(), encoding="utf-8")
    # second write wins by last_seen in fold when both present — use two files
    (inbox / "a@example.com-v2.json").write_text(
        e2.model_dump_json(), encoding="utf-8"
    )

    assert compact_email_index_stations_only(mgr, compactor_id="ci") is True
    current = mgr.index_root / "CURRENT"
    assert current.exists()
    meta = json.loads(current.read_text(encoding="utf-8"))
    assert meta["generation"] == 1
    assert "checkpoint" in meta
    checkpoint = mgr.index_root / meta["checkpoint"]
    assert checkpoint.exists()
    # consuming mode: inbox files removed
    remaining = list(mgr.inbox_dir.rglob("*.json"))
    assert remaining == []


def test_email_compact_single_authority_materializes_shards(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """stations fold wins; shards are projection from CURRENT (phone/address analog)."""
    from cocli.core.stations_runtime import materialize_email_shards_from_current

    campaign = "email-converge"
    camp_dir = tmp_path / "campaigns" / campaign
    camp_dir.mkdir(parents=True)
    monkeypatch.setattr(
        "cocli.core.email_index_manager.get_campaign_dir",
        lambda _name: camp_dir,
    )

    mgr = EmailIndexManager(campaign)
    # Existing cold shard (older)
    old = EmailEntry(
        email="a@example.com",
        domain="example.com",
        source="shard",
        last_seen=datetime(2026, 1, 1, tzinfo=UTC),
    )
    shard_id = mgr.get_shard_id("example.com")
    (mgr.shards_dir / f"{shard_id}.usv").write_text(old.to_usv(), encoding="utf-8")

    # Hot inbox USV (product format) wins by last_seen
    newer = EmailEntry(
        email="a@example.com",
        domain="example.com",
        source="inbox",
        last_seen=datetime(2026, 1, 5, tzinfo=UTC),
    )
    other = EmailEntry(
        email="b@other.com",
        domain="other.com",
        source="inbox",
        last_seen=datetime(2026, 1, 4, tzinfo=UTC),
    )
    mgr.add_email(newer)
    mgr.add_email(other)

    mgr.compact()

    assert (mgr.index_root / "CURRENT").exists()
    # No dual path: inbox empty, shards match CURRENT fold
    assert list(mgr.inbox_dir.rglob("*.usv")) == []
    results = mgr.query()
    by_email = {str(e.email).lower(): e for e in results}
    assert set(by_email) == {"a@example.com", "b@other.com"}
    assert by_email["a@example.com"].source == "inbox"
    assert by_email["a@example.com"].last_seen == datetime(2026, 1, 5, tzinfo=UTC)

    # materialize is idempotent projection
    n = materialize_email_shards_from_current(mgr)
    assert n == 2
