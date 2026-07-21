"""Phase 3: drive cocli work via stations TransformEngine / Compactor.

Thin adapters only — no product Typer/application rewrite (decision 0006).
On-disk layouts stay cocli's; engines own claim→transform→complete and
six-step compaction when given Path* edges.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
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


def compact_email_index(manager: Any, *, compactor_id: Optional[str] = None) -> bool:
    """Compact a campaign email index via stations ``DefaultCompactor``.

    Reads ``indexes/emails/inbox`` as a log, folds LWW by email/last_seen, commits
    ``CURRENT`` + checkpoint under the index root (PHYSICAL-CONTRACT §6), then
    deletes consumed inbox files. Also refreshes legacy ``shards/*.usv`` via the
    existing manager fold so product readers keep working without a format break
    on shard files.
    """
    from cocli.models.campaigns.indexes.email import EmailEntry

    index_root = Path(manager.index_root)
    index_root.mkdir(parents=True, exist_ok=True)
    inbox_dir = index_root / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    backend = LocalPathBackend(index_root)
    # Paths relative to index_root
    inbox_rel = "inbox"

    def ser(entry: Any) -> bytes:
        if isinstance(entry, EmailEntry):
            # Store JSON for stations checkpoint; product shards stay USV via manager
            return entry.model_dump_json().encode("utf-8")
        if isinstance(entry, dict):
            return json.dumps(entry, sort_keys=True).encode("utf-8")
        return json.dumps(entry, default=str, sort_keys=True).encode("utf-8")

    def de(data: bytes) -> Any:
        text = data.decode("utf-8")
        # Prefer JSON; fall back to USV line via EmailEntry if needed
        try:
            raw = json.loads(text)
            if isinstance(raw, dict) and "email" in raw:
                return EmailEntry.model_validate(raw)
            return raw
        except json.JSONDecodeError:
            try:
                return EmailEntry.from_usv(text.strip())
            except Exception:
                return {"raw": text}

    # Materialize inbox files that may be nested by shard as log-readable flat copies
    # PathLogEdge lists under inbox/; USV files work if deserialize handles them.
    log = PathLogEdge(
        station=StationDecl("email-inbox", "inbox", model=EmailEntry),
        backend=backend,
        root=inbox_rel,
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

    def key_fn(r: Any) -> str:
        if isinstance(r, EmailEntry):
            return str(r.email).lower()
        if isinstance(r, dict):
            return str(r.get("email", r.get("id", ""))).lower()
        return str(r)

    def ver_fn(r: Any) -> str:
        if isinstance(r, EmailEntry):
            return str(r.last_seen or r.found_at or "")
        if isinstance(r, dict):
            return str(r.get("last_seen") or r.get("found_at") or "")
        return ""

    fold = last_write_wins_fold(None, key_fn=key_fn, version_fn=ver_fn)
    cid = compactor_id or f"email-{datetime.now(tz=timezone.utc).strftime('%Y%m%d%H%M%S')}"
    compactor = DefaultCompactor(consuming=True)
    committed = compactor.compact_once(
        sources=[log],
        index=index,
        fold=fold,
        compactor_id=cid,
    )

    # Keep legacy shards/ in sync for DuckDB readers (no GM-prospects cutover)
    if committed:
        try:
            manager.compact()
        except Exception as exc:
            logger.warning(
                "stations CURRENT committed but legacy email shard refresh failed: %s",
                exc,
            )
    return committed


def compact_email_index_stations_only(
    manager: Any, *, compactor_id: Optional[str] = None
) -> bool:
    """Like :func:`compact_email_index` but does not call legacy ``manager.compact``.

    Used by CI to prove the stations Compactor path alone produces a CURRENT.
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
