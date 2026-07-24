"""Phase 3: drive cocli work via stations TransformEngine / Compactor.

Thin adapters only — no product Typer/application rewrite (decision 0006).
On-disk layouts stay cocli's; engines own claim→transform→complete and
six-step compaction when given Path* edges.

Phase 4: removed the unused compact_email_index wrapper that re-entered
legacy manager.compact after stations commit (dead code / recursion risk).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Generic, List, Optional, TypeVar

from stations.backends import LocalPathBackend
from stations.compactor import DefaultCompactor, last_write_wins_fold
from stations.edges import PathIndexEdge, PathLogEdge
from stations.engine import DefaultTransformEngine
from stations.station import StationDecl

from cocli.core.stations_adapt import as_queue_edge

logger = logging.getLogger(__name__)

T = TypeVar("T")
U = TypeVar("U")


@dataclass
class _CallbackLogEdge(Generic[U]):
    """LogEdge that delivers transform output to a callback (product side-effect)."""

    station: Any
    backend: Any
    _on_append: Callable[[U], None]
    _appended: List[U]

    def append(self, record: U) -> str:
        self._on_append(record)
        self._appended.append(record)
        return str(len(self._appended))

    def iter_beyond(self, watermark: Optional[object] = None) -> Any:
        _ = watermark
        yield from self._appended


def run_queue_transform_once(
    queue: Any,
    transform: Callable[[T], U],
    *,
    worker_id: str,
    on_output: Optional[Callable[[U], None]] = None,
    model: type = object,
    ttl_seconds: int = 900,
) -> bool:
    """One claim→transform→complete cycle on a cocli CampaignQueueProtocol.

    Uses stations ``DefaultTransformEngine`` solely for the cycle. Sink is a
    callback log (optional); source complete/ack still runs via QueueEdge adapter.
    """
    source = as_queue_edge(queue, model=model)
    station = StationDecl(
        name=f"{getattr(queue, 'queue_name', 'queue')}-out",
        path_template="callback",
        model=object,
    )
    appended: List[Any] = []

    def _default_on_output(_out: U) -> None:
        return None

    sink = _CallbackLogEdge(
        station=station,
        backend=LocalPathBackend(),
        _on_append=on_output or _default_on_output,
        _appended=appended,
    )
    engine = DefaultTransformEngine(default_ttl_seconds=ttl_seconds)
    return engine.run_once(
        source=source,
        transform=transform,
        sink=sink,
        worker_id=worker_id,
        ttl_seconds=ttl_seconds,
    )


def compact_email_index_stations_only(
    manager: Any, *, compactor_id: Optional[str] = None
) -> bool:
    """Compact email index via stations ``DefaultCompactor`` only.

    Commits ``CURRENT`` + checkpoint under the index root (PHYSICAL-CONTRACT §6)
    and deletes consumed inbox files. Does **not** refresh product ``shards/*.usv``;
    callers that need DuckDB-facing shards (e.g. ``EmailIndexManager.compact``)
    run the legacy fold separately after this returns.
    """
    from cocli.models.campaigns.indexes.email import EmailEntry

    index_root = Path(manager.index_root)
    index_root.mkdir(parents=True, exist_ok=True)
    (index_root / "inbox").mkdir(parents=True, exist_ok=True)
    backend = LocalPathBackend(index_root)

    def ser(entry: Any) -> bytes:
        if isinstance(entry, EmailEntry):
            return entry.model_dump_json().encode("utf-8")
        if isinstance(entry, dict):
            return json.dumps(entry, sort_keys=True).encode("utf-8")
        return json.dumps(entry, default=str).encode("utf-8")

    def de(data: bytes) -> Any:
        try:
            raw = json.loads(data.decode("utf-8"))
            if isinstance(raw, dict) and "email" in raw:
                return EmailEntry.model_validate(raw)
            return raw
        except json.JSONDecodeError:
            return {"raw": data.decode("utf-8", errors="replace")}

    log = PathLogEdge(
        station=StationDecl("email-inbox", "inbox", model=EmailEntry),
        backend=backend,
        root="inbox",
        serialize=ser,
        deserialize=de,
    )
    index = PathIndexEdge(
        station=StationDecl("email-index", "emails", model=EmailEntry),
        backend=backend,
        root=".",
        serialize_record=ser,
        deserialize_record=de,
    )
    fold = last_write_wins_fold(
        None,
        key_fn=lambda r: str(
            getattr(r, "email", None)
            or (r.get("email") if isinstance(r, dict) else r)
        ).lower(),
        version_fn=lambda r: str(
            getattr(r, "last_seen", None)
            or (r.get("last_seen") if isinstance(r, dict) else "")
            or ""
        ),
    )
    cid = compactor_id or "email-stations-only"
    return DefaultCompactor(consuming=True).compact_once(
        sources=[log],
        index=index,
        fold=fold,
        compactor_id=cid,
    )


def compact_prospects_index_stations(
    campaign_name: str, *, compactor_id: Optional[str] = None
) -> bool:
    """Compact prospects index via stations DefaultCompactor.

    Folds write-ahead log records into the prospects index under:
    campaigns/{campaign_name}/indexes/google_maps_prospects/prospects.usv
    """
    from cocli.core.paths import paths

    index_dir = paths.campaign(campaign_name).index("google_maps_prospects").path
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "wal").mkdir(parents=True, exist_ok=True)
    backend = LocalPathBackend(index_dir)

    def ser(entry: Any) -> bytes:
        if isinstance(entry, dict):
            return json.dumps(entry, sort_keys=True).encode("utf-8")
        return str(entry).encode("utf-8")

    def de(data: bytes) -> Any:
        try:
            return json.loads(data.decode("utf-8"))
        except Exception:
            return {"raw": data.decode("utf-8", errors="replace")}

    log = PathLogEdge(
        station=StationDecl("prospects-wal", "wal", model=object),
        backend=backend,
        root="wal",
        serialize=ser,
        deserialize=de,
    )
    index = PathIndexEdge(
        station=StationDecl("prospects-index", "google_maps_prospects", model=object),
        backend=backend,
        root=".",
        serialize_record=ser,
        deserialize_record=de,
    )
    fold = last_write_wins_fold(
        None,
        key_fn=lambda r: str(
            getattr(r, "place_id", None)
            or (r.get("place_id") if isinstance(r, dict) else r)
        ),
        version_fn=lambda r: str(
            getattr(r, "updated_at", None)
            or (r.get("updated_at") if isinstance(r, dict) else "")
            or ""
        ),
    )
    cid = compactor_id or "prospects-stations-compactor"
    return DefaultCompactor(consuming=True).compact_once(
        sources=[log],
        index=index,
        fold=fold,
        compactor_id=cid,
    )

