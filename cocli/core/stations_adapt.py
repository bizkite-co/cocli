"""Phase 1 structural adapters: cocli queue/compactor types → stations.protocols.

No behavior change and no on-disk format change (stations decision 0006 Phase 1).
Existing cocli types keep ``push/poll/ack/nack`` and product compact APIs; these
shims present the stations vocabulary (``enqueue/claim/complete``,
``compact_once``) so mypy can verify conformance against ``stations.protocols``.

Do **not** add a parallel protocol zoo here — Protocols live in ``stations``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Generic, Optional, Sequence, Tuple, Type, TypeVar

from stations.protocols import (
    Compactor,
    Fold,
    IndexEdge,
    Lease,
    LogEdge,
    PathBackend,
    QueueEdge,
    Station,
    Transform,
)

from cocli.core.queue.protocol import CampaignQueueProtocol

T = TypeVar("T")
T_in = TypeVar("T_in")
T_out = TypeVar("T_out")


# ---------------------------------------------------------------------------
# Minimal Station / Lease / PathBackend carriers for shims
# ---------------------------------------------------------------------------


@dataclass
class SimpleStation(Generic[T]):
    """Concrete station declaration used by adapters (not a product station registry)."""

    name: str
    path_template: str
    model: Type[T]
    schema_version: str = "1"
    serialization: str = "json-file"
    datapackage_path: Optional[str] = None

    def resolve(self, **params: str) -> str:
        out = self.path_template
        for key, value in params.items():
            out = out.replace("{" + key + "}", value)
        return out


@dataclass
class SimpleLease:
    worker_id: str
    claimed_at: datetime
    expires_at: datetime
    attempt: int
    item_id: str


class UnwiredPathBackend:
    """Placeholder PathBackend until stations backends land (Phase 2).

    Satisfies the Protocol for typing; methods raise if called so Phase 1
    cannot accidentally pretend storage is wired.
    """

    def exists(self, path: str) -> bool:
        raise NotImplementedError("stations PathBackend not wired (Phase 1 types only)")

    def read_bytes(self, path: str) -> bytes:
        raise NotImplementedError("stations PathBackend not wired (Phase 1 types only)")

    def write_atomic(self, path: str, data: bytes) -> None:
        raise NotImplementedError("stations PathBackend not wired (Phase 1 types only)")

    def list(self, prefix: str) -> Any:
        raise NotImplementedError("stations PathBackend not wired (Phase 1 types only)")
        yield  # pragma: no cover — makes this a generator type for Iterator[str]

    def delete(self, path: str) -> None:
        raise NotImplementedError("stations PathBackend not wired (Phase 1 types only)")

    def create_if_absent(self, path: str, data: bytes) -> bool:
        raise NotImplementedError("stations PathBackend not wired (Phase 1 types only)")

    def replace_if_match(
        self, path: str, data: bytes, *, etag: Optional[str]
    ) -> bool:
        raise NotImplementedError("stations PathBackend not wired (Phase 1 types only)")


# ---------------------------------------------------------------------------
# Queue: CampaignQueueProtocol (push/poll/ack/nack) → QueueEdge
# ---------------------------------------------------------------------------


def _item_id(item: Any) -> str:
    for attr in ("task_id", "id", "place_id", "message_id"):
        val = getattr(item, attr, None)
        if val is not None:
            return str(val)
    return str(id(item))


@dataclass
class CampaignQueueAsQueueEdge(Generic[T]):
    """Adapt cocli ``CampaignQueueProtocol`` to stations ``QueueEdge``.

    Maps: enqueue←push, claim←poll, complete←ack, fail←nack.
    """

    queue: CampaignQueueProtocol[T]
    station: Station[T]
    backend: PathBackend = field(default_factory=UnwiredPathBackend)
    _open_leases: dict[str, SimpleLease] = field(default_factory=dict)

    def enqueue(self, item: T) -> str:
        result = self.queue.push(item)
        return str(result) if result is not None else _item_id(item)

    def claim(
        self, *, worker_id: str, ttl_seconds: int
    ) -> Optional[Tuple[T, Lease]]:
        batch = self.queue.poll(batch_size=1)
        if not batch:
            return None
        item = batch[0]
        now = datetime.now(timezone.utc)
        lease = SimpleLease(
            worker_id=worker_id,
            claimed_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
            attempt=1,
            item_id=_item_id(item),
        )
        self._open_leases[lease.item_id] = lease
        return item, lease

    def complete(
        self, item: T, lease: Lease, result: Optional[object] = None
    ) -> None:
        _ = result
        self.queue.ack(item)
        self._open_leases.pop(lease.item_id, None)

    def fail(self, item: T, lease: Lease, error: object) -> None:
        _ = error
        self.queue.nack(item)
        self._open_leases.pop(lease.item_id, None)

    def renew(self, lease: Lease, *, ttl_seconds: int) -> bool:
        # CampaignQueueProtocol has no lease renew surface; product queues use heartbeat.
        now = datetime.now(timezone.utc)
        updated = SimpleLease(
            worker_id=lease.worker_id,
            claimed_at=lease.claimed_at,
            expires_at=now + timedelta(seconds=ttl_seconds),
            attempt=lease.attempt,
            item_id=lease.item_id,
        )
        self._open_leases[lease.item_id] = updated
        return True


def as_queue_edge(
    queue: CampaignQueueProtocol[T],
    *,
    station_name: Optional[str] = None,
    model: Type[T] = object,  # type: ignore[assignment]
) -> QueueEdge[T]:
    """Return a ``QueueEdge`` view of a cocli campaign queue (mypy gate)."""
    name = station_name or f"{queue.campaign_name}/{queue.queue_name}"
    station: Station[T] = SimpleStation(
        name=name,
        path_template="campaigns/{campaign}/queues/{queue}/pending",
        model=model,
        serialization="json-file",
    )
    edge: QueueEdge[T] = CampaignQueueAsQueueEdge(
        queue=queue, station=station, backend=UnwiredPathBackend()
    )
    return edge


# ---------------------------------------------------------------------------
# Compactor: product compact APIs → Compactor.compact_once
# ---------------------------------------------------------------------------


@dataclass
class CallableAsCompactor:
    """Wrap a zero-arg compact callable as stations ``Compactor``."""

    _run: Callable[[], None]
    name: str = "callable-compactor"

    def compact_once(
        self,
        *,
        sources: Sequence[LogEdge[object]],
        index: IndexEdge[object],
        fold: Fold[object, object],
        compactor_id: str,
    ) -> bool:
        # Phase 1: existing product path; stations args unused until Phase 3.
        _ = sources, index, fold, compactor_id
        self._run()
        return True


def as_compactor(run: Callable[[], None], *, name: str = "compactor") -> Compactor:
    """Return a ``Compactor`` view of an existing compact entrypoint (mypy gate)."""
    c: Compactor = CallableAsCompactor(_run=run, name=name)
    return c


def compact_manager_as_compactor(manager: Any) -> Compactor:
    """Adapt ``CompactManager`` (``run()``) to ``Compactor``."""
    return as_compactor(manager.run, name="CompactManager")


def email_index_as_compactor(manager: Any) -> Compactor:
    """Adapt ``EmailIndexManager`` (``compact()``) to ``Compactor``."""
    return as_compactor(manager.compact, name="EmailIndexManager")


def domain_index_as_compactor(manager: Any) -> Compactor:
    """Adapt ``DomainIndexManager`` (``compact_inbox()``) to ``Compactor``."""
    return as_compactor(manager.compact_inbox, name="DomainIndexManager")


# ---------------------------------------------------------------------------
# Transform: pure callables already structural; helper for mypy gates
# ---------------------------------------------------------------------------


def as_transform(fn: Callable[[T_in], T_out]) -> Transform[T_in, T_out]:
    """Mark a pure model-to-model function as a stations ``Transform``."""
    t: Transform[T_in, T_out] = fn
    return t


# ---------------------------------------------------------------------------
# Conformance helpers (used by tests / mypy)
# ---------------------------------------------------------------------------


def accept_queue_edge(edge: QueueEdge[Any]) -> QueueEdge[Any]:
    """Type gate: argument must satisfy ``QueueEdge``."""
    return edge


def accept_compactor(compactor: Compactor) -> Compactor:
    """Type gate: argument must satisfy ``Compactor``."""
    return compactor


def accept_transform(transform: Transform[Any, Any]) -> Transform[Any, Any]:
    """Type gate: argument must satisfy ``Transform``."""
    return transform


def accept_path_backend(backend: PathBackend) -> PathBackend:
    """Type gate: argument must satisfy ``PathBackend``."""
    return backend


def accept_station(station: Station[Any]) -> Station[Any]:
    """Type gate: argument must satisfy ``Station``."""
    return station
