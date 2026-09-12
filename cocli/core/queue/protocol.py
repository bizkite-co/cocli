"""Product queue names (push/poll/ack/nack) plus QueueEdge aliases.

Filesystem queues satisfy ``stations.protocols.QueueEdge`` directly via
:class:`QueueEdgeAliasesMixin` (enqueue/claim/complete/fail/renew). Product
workers keep push/poll/ack. Do not add a wrapper class in stations_adapt
and do not redefine stations Protocols here (decision 0007).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Protocol, TypeVar

from stations.protocols import Lease

from cocli.core.ordinant import StateFolder

T = TypeVar("T")


class CampaignQueueProtocol(Protocol[T]):
    """Product vocabulary used by workers and SQS families."""

    campaign_name: str
    queue_name: str

    def push(self, task: T) -> Any: ...
    def poll(self, batch_size: int = 1) -> list[T]: ...
    def ack(self, task: T) -> None: ...
    def nack(self, task: T, is_http_500: bool = False) -> None: ...
    def count_state(self, state: StateFolder) -> int: ...


@dataclass
class SimpleLease:
    """Lease carrier for QueueEdge.claim; disk CAS stays on the product queue."""

    worker_id: str
    claimed_at: datetime
    expires_at: datetime
    attempt: int
    item_id: str


def _item_id(item: Any) -> str:
    for attr in ("task_id", "id", "place_id", "message_id", "ack_token"):
        val = getattr(item, attr, None)
        if val is not None:
            return str(val)
    return str(id(item))


class QueueEdgeAliasesMixin:
    """Native QueueEdge on types that already implement push/poll/ack/nack.

    Host must provide ``station``, ``backend``, ``push``, ``poll``, ``ack``,
    and ``nack``. TransformEngine uses enqueue/claim/complete; workers keep
    poll/ack.
    """

    station: Any
    backend: Any

    def enqueue(self, item: Any) -> str:
        result = self.push(item)  # type: ignore[attr-defined]
        return str(result) if result is not None else _item_id(item)

    def claim(
        self, *, worker_id: str, ttl_seconds: int
    ) -> Optional[tuple[Any, Lease]]:
        batch = self.poll(batch_size=1)  # type: ignore[attr-defined]
        if not batch:
            return None
        item = batch[0]
        now = datetime.now(timezone.utc)
        lease: Lease = SimpleLease(
            worker_id=worker_id,
            claimed_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
            attempt=1,
            item_id=_item_id(item),
        )
        return item, lease

    def complete(
        self, item: Any, lease: Lease, result: Optional[object] = None
    ) -> None:
        _ = result
        self.ack(item)  # type: ignore[attr-defined]
        _ = lease

    def fail(self, item: Any, lease: Lease, error: object) -> None:
        _ = error, lease
        nack = getattr(self, "nack", None)
        if nack is not None:
            nack(item)

    def renew(self, lease: Lease, *, ttl_seconds: int) -> bool:
        _ = lease, ttl_seconds
        return True

