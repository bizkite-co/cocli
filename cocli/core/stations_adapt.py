"""Structural adapters: cocli compact/transform types → stations.protocols.

Filesystem queues satisfy ``QueueEdge`` themselves (``QueueEdgeAliasesMixin``).
Compactor shims remain for product compact entrypoints. Claim/lease CAS is
owned by ``stations.backends``. Do **not** add a parallel protocol zoo —
Protocols live in ``stations`` (decision 0007).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Generic, Optional, Sequence, TypeVar

from stations.protocols import (
    Compactor,
    Fold,
    IndexEdge,
    LogEdge,
    PathBackend,
    QueueEdge,
    Station,
    Transform,
)

T = TypeVar("T")
T_in = TypeVar("T_in")
T_out = TypeVar("T_out")


# ---------------------------------------------------------------------------
# Minimal Station / Lease carriers for shims
# ---------------------------------------------------------------------------


@dataclass
class SimpleStation(Generic[T]):
    """Concrete station declaration used by adapters (not a product station registry)."""

    name: str
    path_template: str
    model: type[T]
    schema_version: str = "1"
    serialization: str = "json-file"
    datapackage_path: Optional[str] = None

    def resolve(self, **params: str) -> str:
        out = self.path_template
        for key, value in params.items():
            out = out.replace("{" + key + "}", value)
        return out


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


def accept_log_edge(edge: LogEdge[Any]) -> LogEdge[Any]:
    """Type gate: argument must satisfy ``LogEdge`` (e.g. entity field journal)."""
    return edge
