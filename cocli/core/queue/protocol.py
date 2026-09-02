"""Product queue Protocol (push/poll/ack/nack).

Stations vocabulary uses enqueue/claim/complete (see ``stations.protocols.QueueEdge``).
Adapt with :func:`cocli.core.stations_adapt.as_queue_edge` (strangler Phase 1).
Do not redefine stations Protocols here — stations decision 0007.
"""

from typing import Any, Protocol, TypeVar
from cocli.core.ordinant import StateFolder

T = TypeVar("T")


class CampaignQueueProtocol(Protocol[T]):
    campaign_name: str
    queue_name: str

    def push(self, task: T) -> Any: ...
    def poll(self, batch_size: int = 1) -> list[T]: ...
    def ack(self, task: T) -> None: ...
    def nack(self, task: T, is_http_500: bool = False) -> None: ...
    def count_state(self, state: StateFolder) -> int: ...

