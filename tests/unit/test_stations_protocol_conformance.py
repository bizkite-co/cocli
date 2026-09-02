"""Phase 1: cocli types satisfy stations.protocols via structural adapters."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from stations.backends import LocalPathBackend
from stations.protocols import Compactor, QueueEdge, Transform

from cocli.core.stations_adapt import (
    SimpleStation,
    accept_compactor,
    accept_path_backend,
    accept_queue_edge,
    accept_station,
    accept_transform,
    as_compactor,
    as_queue_edge,
    as_transform,
    compact_manager_as_compactor,
    domain_index_as_compactor,
    email_index_as_compactor,
)


class _FakeTask:
    def __init__(self, task_id: str) -> None:
        self.task_id = task_id


class _FakeQueue:
    """Minimal CampaignQueueProtocol stand-in."""

    campaign_name = "roadmap"
    queue_name = "gm-list"

    def __init__(self) -> None:
        self._items: list[_FakeTask] = []
        self.acked: list[_FakeTask] = []
        self.nacked: list[_FakeTask] = []

    def push(self, task: _FakeTask) -> Any:
        self._items.append(task)
        return task.task_id

    def poll(self, batch_size: int = 1) -> list[_FakeTask]:
        out = self._items[:batch_size]
        self._items = self._items[batch_size:]
        return out

    def ack(self, task: _FakeTask) -> None:
        self.acked.append(task)

    def nack(self, task: _FakeTask, is_http_500: bool = False) -> None:
        _ = is_http_500
        self.nacked.append(task)


def test_stations_local_backend_is_path_backend() -> None:
    """Phase 4: PathBackend comes from stations (not a cocli Unwired placeholder)."""
    backend = accept_path_backend(LocalPathBackend())
    assert backend is not None


def test_simple_station_is_station() -> None:
    station = SimpleStation(
        name="test",
        path_template="queues/{name}/pending",
        model=_FakeTask,
    )
    accept_station(station)
    assert station.resolve(name="gm-list") == "queues/gm-list/pending"


def test_queue_adapter_satisfies_queue_edge() -> None:
    q = _FakeQueue()
    edge = as_queue_edge(q, station_name="roadmap/gm-list", model=_FakeTask)
    # mypy gate
    typed: QueueEdge[_FakeTask] = accept_queue_edge(edge)

    item_id = typed.enqueue(_FakeTask("t1"))
    assert item_id == "t1"

    claimed = typed.claim(worker_id="w1", ttl_seconds=60)
    assert claimed is not None
    item, lease = claimed
    assert item.task_id == "t1"
    assert lease.worker_id == "w1"

    typed.complete(item, lease)
    assert q.acked == [item]

    # fail path
    typed.enqueue(_FakeTask("t2"))
    claimed2 = typed.claim(worker_id="w1", ttl_seconds=30)
    assert claimed2 is not None
    item2, lease2 = claimed2
    typed.fail(item2, lease2, error=RuntimeError("x"))
    assert q.nacked == [item2]


def test_queue_claim_empty() -> None:
    edge = as_queue_edge(_FakeQueue(), model=_FakeTask)
    assert edge.claim(worker_id="w", ttl_seconds=10) is None


def test_callable_as_compactor() -> None:
    calls: list[str] = []

    def run() -> None:
        calls.append("ran")

    c = as_compactor(run, name="test")
    typed: Compactor = accept_compactor(c)
    assert typed.compact_once(
        sources=[],
        index=MagicMock(),
        fold=lambda records: records,
        compactor_id="c1",
    )
    assert calls == ["ran"]


def test_product_compactor_adapters() -> None:
    mgr = MagicMock()
    accept_compactor(compact_manager_as_compactor(mgr)).compact_once(
        sources=[], index=MagicMock(), fold=lambda r: r, compactor_id="x"
    )
    mgr.run.assert_called_once()

    email = MagicMock()
    accept_compactor(email_index_as_compactor(email)).compact_once(
        sources=[], index=MagicMock(), fold=lambda r: r, compactor_id="x"
    )
    email.compact.assert_called_once()

    domain = MagicMock()
    accept_compactor(domain_index_as_compactor(domain)).compact_once(
        sources=[], index=MagicMock(), fold=lambda r: r, compactor_id="x"
    )
    domain.compact_inbox.assert_called_once()


def test_pure_function_is_transform() -> None:
    def slugify_name(raw: str) -> str:
        return raw.strip().lower().replace(" ", "-")

    t: Transform[str, str] = accept_transform(as_transform(slugify_name))
    assert t("Hello World") == "hello-world"


def test_campaign_queue_protocol_module_documents_mapping() -> None:
    """Ensure legacy protocol module still exists (not deleted by extraction)."""
    from cocli.core.queue.protocol import CampaignQueueProtocol

    assert hasattr(CampaignQueueProtocol, "push")
    assert hasattr(CampaignQueueProtocol, "poll")
