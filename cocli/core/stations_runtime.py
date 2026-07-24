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
from cocli.station_defs.campaigns.indexes.emails import (
    EMAIL_INBOX,
    EMAIL_INDEX,
    EMAIL_SHARDS,
)

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


def _email_entry_ser(entry: Any) -> bytes:
    from cocli.models.campaigns.indexes.email import EmailEntry

    if isinstance(entry, EmailEntry):
        return entry.model_dump_json().encode("utf-8")
    if isinstance(entry, dict):
        return json.dumps(entry, sort_keys=True, default=str).encode("utf-8")
    return json.dumps(entry, default=str).encode("utf-8")


def _email_entry_de(data: bytes) -> Any:
    """Deserialize inbox file bytes: JSON checkpoint lines or product USV."""
    from cocli.models.campaigns.indexes.email import EmailEntry

    text = data.decode("utf-8", errors="replace").strip()
    if not text:
        return {"raw": ""}
    try:
        raw = json.loads(text)
        if isinstance(raw, dict) and "email" in raw:
            return EmailEntry.model_validate(raw)
        return raw
    except json.JSONDecodeError:
        pass
    try:
        return EmailEntry.from_usv(text)
    except Exception:
        return {"raw": text}


def _email_key(r: Any) -> str:
    return str(
        getattr(r, "email", None) or (r.get("email") if isinstance(r, dict) else r)
    ).lower()


def _email_version(r: Any) -> str:
    return str(
        getattr(r, "last_seen", None)
        or (r.get("last_seen") if isinstance(r, dict) else "")
        or ""
    )


@dataclass
class _UsvShardDirectoryLogEdge:
    """Read-only LogEdge: yield EmailEntry lines from ``shards/*.usv``.

    No ``root`` for DefaultCompactor path-delete — shards are rewritten after
    fold from CURRENT, not deleted as source files mid-cycle.
    """

    station: Any
    backend: Any
    shards_dir: Path

    def append(self, record: Any) -> str:
        raise NotImplementedError("email shard log is a compact source only")

    def iter_beyond(self, watermark: Optional[object] = None) -> Any:
        _ = watermark
        from cocli.models.campaigns.indexes.email import EmailEntry

        if not self.shards_dir.exists():
            return
        for path in sorted(self.shards_dir.glob("*.usv")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("skip shard %s: %s", path, exc)
                continue
            for line in text.splitlines():
                if not line.strip():
                    continue
                try:
                    yield EmailEntry.from_usv(line)
                except Exception as exc:
                    logger.warning("skip non-conforming email line in %s: %s", path, exc)


def compact_email_index_stations_only(
    manager: Any, *, compactor_id: Optional[str] = None
) -> bool:
    """Compact email index via stations ``DefaultCompactor`` (single fold authority).

    Sources: product inbox (consuming) + existing ``shards/*.usv`` (retained read).
    Commits ``CURRENT`` + checkpoint (PHYSICAL-CONTRACT §6). Inbox files are
    deleted post-commit; shards are **not** deleted here — call
    :func:`materialize_email_shards_from_current` so DuckDB readers see the same
    fold as CURRENT (no second independent LWW).
    """

    index_root = Path(manager.index_root)
    index_root.mkdir(parents=True, exist_ok=True)
    (index_root / "inbox").mkdir(parents=True, exist_ok=True)
    shards_dir = Path(manager.shards_dir)
    shards_dir.mkdir(parents=True, exist_ok=True)
    backend = LocalPathBackend(index_root)

    inbox_log = PathLogEdge(
        station=EMAIL_INBOX,
        backend=backend,
        root="inbox",
        serialize=_email_entry_ser,
        deserialize=_email_entry_de,
    )
    shard_log = _UsvShardDirectoryLogEdge(
        station=EMAIL_SHARDS,
        backend=backend,
        shards_dir=shards_dir,
    )
    index = PathIndexEdge(
        station=EMAIL_INDEX,
        backend=backend,
        root=".",
        serialize_record=_email_entry_ser,
        deserialize_record=_email_entry_de,
    )
    fold = last_write_wins_fold(
        None,
        key_fn=_email_key,
        version_fn=_email_version,
    )
    cid = compactor_id or "email-stations-only"
    return DefaultCompactor(consuming=True).compact_once(
        sources=[inbox_log, shard_log],
        index=index,
        fold=fold,
        compactor_id=cid,
    )


def load_email_entries_from_current(manager: Any) -> List[Any]:
    """Load folded EmailEntry list from stations CURRENT checkpoint."""
    from cocli.models.campaigns.indexes.email import EmailEntry

    index_root = Path(manager.index_root)
    if not (index_root / "CURRENT").exists():
        return []
    backend = LocalPathBackend(index_root)
    index = PathIndexEdge(
        station=EMAIL_INDEX,
        backend=backend,
        root=".",
        serialize_record=_email_entry_ser,
        deserialize_record=_email_entry_de,
    )
    base = index.read_current()
    if base is None:
        return []
    if isinstance(base, list):
        out: List[Any] = []
        for item in base:
            if isinstance(item, EmailEntry):
                out.append(item)
            elif isinstance(item, dict) and "email" in item:
                try:
                    out.append(EmailEntry.model_validate(item))
                except Exception:
                    pass
        return out
    if isinstance(base, EmailEntry):
        return [base]
    return []


def materialize_email_shards_from_current(manager: Any) -> int:
    """Rewrite ``shards/*.usv`` from stations CURRENT (DuckDB-facing materialization).

    Single authority: stations fold already ran; this is pure projection, not a
    second LWW over inbox+shards.
    """
    from cocli.models.campaigns.indexes.email import EmailEntry

    entries = load_email_entries_from_current(manager)
    shards_dir = Path(manager.shards_dir)
    shards_dir.mkdir(parents=True, exist_ok=True)

    # Clear prior shards then rewrite from CURRENT
    for old in shards_dir.glob("*.usv"):
        try:
            old.unlink()
        except OSError as exc:
            logger.warning("could not remove old email shard %s: %s", old, exc)

    if not entries:
        return 0

    groups: dict[str, List[Any]] = {}
    for entry in entries:
        if not isinstance(entry, EmailEntry):
            continue
        shard_id = manager.get_shard_id(entry.domain)
        groups.setdefault(shard_id, []).append(entry)

    for shard_id, group in groups.items():
        shard_path = shards_dir / f"{shard_id}.usv"
        with open(shard_path, "w", encoding="utf-8") as f:
            for entry in group:
                f.write(entry.to_usv())
        logger.info(
            "materialized email shard %s (%s) count=%s",
            shard_id,
            shard_path,
            len(group),
        )
    return len(entries)


# Canonical column set for google_maps_prospects USV (headerless) DuckDB fold.
_PROSPECTS_USV_COLUMNS: dict[str, str] = {
    "place_id": "VARCHAR",
    "company_slug": "VARCHAR",
    "name": "VARCHAR",
    "phone_1": "VARCHAR",
    "created_at": "VARCHAR",
    "updated_at": "VARCHAR",
    "version": "INTEGER",
    "keyword": "VARCHAR",
    "full_address": "VARCHAR",
    "street_address": "VARCHAR",
    "city": "VARCHAR",
    "zip": "VARCHAR",
    "municipality": "VARCHAR",
    "state": "VARCHAR",
    "country": "VARCHAR",
    "timezone": "VARCHAR",
    "phone_standard_format": "VARCHAR",
    "website": "VARCHAR",
    "domain": "VARCHAR",
    "first_category": "VARCHAR",
    "second_category": "VARCHAR",
    "claimed_google_my_business": "VARCHAR",
    "reviews_count": "INTEGER",
    "average_rating": "DOUBLE",
    "hours": "VARCHAR",
    "saturday": "VARCHAR",
    "sunday": "VARCHAR",
    "monday": "VARCHAR",
    "tuesday": "VARCHAR",
    "wednesday": "VARCHAR",
    "thursday": "VARCHAR",
    "friday": "VARCHAR",
    "latitude": "DOUBLE",
    "longitude": "DOUBLE",
    "coordinates": "VARCHAR",
    "plus_code": "VARCHAR",
    "menu_link": "VARCHAR",
    "gmb_url": "VARCHAR",
    "cid": "VARCHAR",
    "google_knowledge_url": "VARCHAR",
    "kgmid": "VARCHAR",
    "image_url": "VARCHAR",
    "favicon": "VARCHAR",
    "review_url": "VARCHAR",
    "facebook_url": "VARCHAR",
    "linkedin_url": "VARCHAR",
    "instagram_url": "VARCHAR",
    "thumbnail_url": "VARCHAR",
    "reviews": "VARCHAR",
    "quotes": "VARCHAR",
    "uuid": "VARCHAR",
    "company_hash": "VARCHAR",
    "discovery_phrase": "VARCHAR",
    "discovery_tile_id": "VARCHAR",
    "processed_by": "VARCHAR",
}


def _collect_prospect_usv_sources(
    index_dir: Path,
    *,
    checkpoint_path: Path,
    staging_dirs: Optional[List[Path]] = None,
) -> List[Path]:
    """Local USV sources for fold: wal/**, staging/**, naked root (not checkpoint)."""
    files: List[Path] = []
    wal = index_dir / "wal"
    if wal.exists():
        files.extend(sorted(wal.rglob("*.usv")))
    for staging in staging_dirs or []:
        if staging and Path(staging).exists():
            files.extend(sorted(Path(staging).rglob("*.usv")))
    ck_name = checkpoint_path.name
    for f_path in sorted(index_dir.glob("*.usv")):
        if f_path.name in (ck_name, "validation_errors.usv"):
            continue
        if f_path.name.startswith("checkpoint."):
            continue
        files.append(f_path)
    # Existing product checkpoint is the base generation (retained input)
    if checkpoint_path.exists() and checkpoint_path.stat().st_size > 0:
        files.append(checkpoint_path)
    # de-dupe preserving order
    seen: set[Path] = set()
    out: List[Path] = []
    for p in files:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            out.append(p)
    return out


def _duckdb_fold_prospect_usv_files(
    source_files: List[Path], dest: Path
) -> bool:
    """Deterministic LWW fold by place_id / updated_at (product-scale Fold)."""
    import duckdb

    if not source_files:
        return False
    path_list = "', '".join(str(p) for p in source_files)
    cols = json.dumps(_PROSPECTS_USV_COLUMNS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    con = duckdb.connect(database=":memory:")
    q = f"""
        COPY (
            SELECT * EXCLUDE (row_num) FROM (
                SELECT *,
                       row_number() OVER (
                           PARTITION BY place_id ORDER BY updated_at DESC
                       ) as row_num
                FROM read_csv(
                    ['{path_list}'],
                    delim='\x1f',
                    header=False,
                    columns={cols},
                    ignore_errors=True
                )
            )
            WHERE row_num = 1
        ) TO '{tmp}' (DELIMITER '\x1f', HEADER FALSE)
    """
    con.execute(q)
    if not tmp.exists():
        return False
    tmp.replace(dest)
    return dest.exists() and dest.stat().st_size >= 0


def _stations_cas_commit_current(
    index_dir: Path,
    *,
    checkpoint_rel: str,
    checkpoint_bytes: bytes,
    compactor_id: str,
) -> bool:
    """Six-step-ish CURRENT CAS via stations PathBackend (CONCURRENCY §3–4)."""
    from datetime import datetime, timezone

    from stations.backends.etag import content_etag
    from stations.protect import protect_path

    backend = LocalPathBackend(index_dir)
    current_path = "CURRENT"
    generation = 0
    if backend.exists(current_path):
        try:
            meta = json.loads(backend.read_bytes(current_path).decode("utf-8"))
            generation = int(meta.get("generation") or 0)
        except Exception:
            generation = 0
    new_gen = generation + 1
    # Prefer generation-stamped name when caller passes template
    if "{gen}" in checkpoint_rel:
        checkpoint_rel = checkpoint_rel.format(gen=new_gen)
    backend.write_atomic(checkpoint_rel, checkpoint_bytes)
    new_meta = {
        "generation": new_gen,
        "checkpoint": checkpoint_rel,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "compactor_id": compactor_id,
        "mode": "consuming",
        "content_hash": content_etag(checkpoint_bytes),
        "format": "usv",
    }
    new_bytes = json.dumps(new_meta, sort_keys=True).encode("utf-8")
    if backend.exists(current_path):
        etag = content_etag(backend.read_bytes(current_path))
        ok = backend.replace_if_match(current_path, new_bytes, etag=etag)
        if not ok:
            try:
                backend.delete(checkpoint_rel)
            except Exception:
                pass
            logger.warning("prospects CURRENT CAS lost; abandoning gen=%s", new_gen)
            return False
    else:
        if not backend.create_if_absent(current_path, new_bytes):
            try:
                backend.delete(checkpoint_rel)
            except Exception:
                pass
            return False
    # Mechanical protect on ratified artifacts
    try:
        protect_path(index_dir / checkpoint_rel)
        protect_path(index_dir / "CURRENT")
    except Exception as exc:
        logger.debug("protect after CURRENT commit: %s", exc)
    return True


def materialize_prospects_usv_from_checkpoint(
    index_dir: Path,
    *,
    checkpoint_path: Path,
    generation_file: Path,
) -> None:
    """Copy generation checkpoint to stable product path ``prospects.usv`` + protect."""
    import shutil

    from stations.protect import protect_path, unprotect_for_write

    if not generation_file.exists():
        return
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    if checkpoint_path.exists():
        unprotect_for_write(checkpoint_path)
    shutil.copy2(generation_file, checkpoint_path)
    protect_path(checkpoint_path)
    logger.info("materialized prospects USV at %s", checkpoint_path)


def compact_prospects_local(
    index_dir: Path,
    *,
    checkpoint_path: Path,
    staging_dirs: Optional[List[Path]] = None,
    compactor_id: Optional[str] = None,
) -> bool:
    """Local prospects compact: DuckDB LWW fold + stations CURRENT CAS + materialize.

    DefaultCompactor loads all records in-process; prospect indexes are large, so the
    fold is DuckDB (deterministic C7) while commit/protect use stations PathBackend.
    WAL / naked / staging USVs are inputs; stable product file is ``checkpoint_path``
    (typically ``prospects.usv`` via IndexPaths).
    """
    index_dir = Path(index_dir)
    checkpoint_path = Path(checkpoint_path)
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "wal").mkdir(parents=True, exist_ok=True)

    sources = _collect_prospect_usv_sources(
        index_dir,
        checkpoint_path=checkpoint_path,
        staging_dirs=staging_dirs,
    )
    # Need WAL/staging/naked inputs beyond an unchanged sole checkpoint
    non_ck = [p for p in sources if p.resolve() != checkpoint_path.resolve()]
    if not non_ck:
        logger.info("prospects compact: no WAL/staging sources; idle")
        return False

    cid = compactor_id or "prospects-stations"
    folded = index_dir / f".fold-{cid}.usv"
    try:
        if not _duckdb_fold_prospect_usv_files(sources, folded):
            logger.info("prospects compact: DuckDB fold produced no output")
            return False
        body = folded.read_bytes()
        backend = LocalPathBackend(index_dir)
        generation = 0
        if backend.exists("CURRENT"):
            try:
                generation = int(
                    json.loads(backend.read_bytes("CURRENT").decode("utf-8")).get(
                        "generation"
                    )
                    or 0
                )
            except Exception:
                generation = 0
        new_gen = generation + 1
        gen_rel = f"checkpoint.{new_gen:06d}.usv"
        if not _stations_cas_commit_current(
            index_dir,
            checkpoint_rel=gen_rel,
            checkpoint_bytes=body,
            compactor_id=cid,
        ):
            return False
        materialize_prospects_usv_from_checkpoint(
            index_dir,
            checkpoint_path=checkpoint_path,
            generation_file=index_dir / gen_rel,
        )
        # Consume local WAL / naked sources (not the product checkpoint)
        import shutil

        wal = index_dir / "wal"
        if wal.exists():
            shutil.rmtree(wal)
            wal.mkdir(parents=True, exist_ok=True)
        ck_name = checkpoint_path.name
        for f_path in list(index_dir.glob("*.usv")):
            if f_path.name in (ck_name, "validation_errors.usv"):
                continue
            if f_path.name.startswith("checkpoint."):
                continue
            if f_path.name.startswith(".fold-"):
                f_path.unlink(missing_ok=True)
                continue
            f_path.unlink(missing_ok=True)
        logger.info(
            "prospects stations compact ok gen=%s sources=%s id=%s",
            new_gen,
            len(sources),
            cid,
        )
        return True
    finally:
        if folded.exists():
            try:
                folded.unlink()
            except OSError:
                pass


def compact_prospects_index_stations(
    campaign_name: str,
    *,
    staging_dir: Optional[Path] = None,
    compactor_id: Optional[str] = None,
) -> bool:
    """Compact google_maps_prospects for a campaign via stations commit path."""
    from cocli.core.paths import paths

    idx = paths.campaign(campaign_name).index("google_maps_prospects")
    staging_dirs = [Path(staging_dir)] if staging_dir else None
    return compact_prospects_local(
        idx.path,
        checkpoint_path=idx.checkpoint,
        staging_dirs=staging_dirs,
        compactor_id=compactor_id,
    )

