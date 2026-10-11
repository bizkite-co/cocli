"""Stations LogEdge for the cocli entity field journal (decision 0009).

Preserves Shape A on-disk layout (``{date}_{node_id}.usv`` multi-record
segments under ``paths.wal``). Field-update facts are whole log records;
compaction folds them (LWW per target+field) and writes whole entity state.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

import yaml
from stations.backends import LocalPathBackend
from stations.compactor import last_write_wins_fold

from cocli.core.paths import paths
from cocli.models.wal.record import RS, DatagramRecord
from cocli.station_defs.wal.entity_field import ENTITY_FIELD_JOURNAL

logger = logging.getLogger(__name__)


def _station() -> Any:
    return ENTITY_FIELD_JOURNAL


@dataclass
class EntityFieldLogEdge:
    """``LogEdge[DatagramRecord]`` over the centralized Shape A entity journal.

    ``backend`` satisfies the protocol; append/iter use cocli ``paths.wal``
    layout (segment files), not PathLogEdge Shape B file-per-record.
    """

    station: Any = field(default_factory=_station)
    backend: Any = field(default_factory=LocalPathBackend)
    wal_root: Optional[Path] = None

    def _root(self) -> Path:
        if self.wal_root is not None:
            return self.wal_root
        # DataPaths.wal is WalPaths; .path is the directory
        return Path(paths.wal.path)

    def append(self, record: DatagramRecord) -> str:
        """Append-only write into the node's Shape A segment (P7)."""
        root = self._root()
        root.mkdir(parents=True, exist_ok=True)
        segment = root / f"{_period_day()}_{record.node_id}.usv"
        with open(segment, "a", encoding="utf-8") as f:
            f.write(record.to_usv())
        logger.info(
            "entity field log append: %s.%s in %s",
            record.target,
            record.field,
            segment,
        )
        return segment.name

    def iter_beyond(self, watermark: Optional[object] = None) -> Iterator[DatagramRecord]:
        """Yield field-update facts; optional watermark is segment filename(s)."""
        root = self._root()
        if not root.exists():
            return
        seen = _watermark_set(watermark)
        for wal_file in sorted(root.glob("*.usv")):
            if wal_file.name in seen or str(wal_file) in seen:
                continue
            # Skip stations fold artifacts if ever co-located
            if wal_file.name.startswith("checkpoint."):
                continue
            try:
                content = wal_file.read_text(encoding="utf-8")
            except OSError as exc:
                logger.error("Error reading entity field journal %s: %s", wal_file, exc)
                continue
            for raw in content.split(RS):
                if not raw.strip():
                    continue
                try:
                    yield DatagramRecord.from_usv(raw)
                except Exception as exc:
                    logger.warning(
                        "skip non-conforming field-update in %s: %s", wal_file, exc
                    )


def open_entity_field_log(*, wal_root: Optional[Path] = None) -> EntityFieldLogEdge:
    """Return a stations-conforming LogEdge for the entity field journal."""
    return EntityFieldLogEdge(wal_root=wal_root)


def field_update_key(record: DatagramRecord) -> str:
    """LWW identity: one winner per (entity target, field)."""
    return f"{record.target}\x1f{record.field}"


def field_update_version(record: DatagramRecord) -> str:
    return record.timestamp


def field_updates_fold() -> Any:
    """Pure C7 fold: last-write-wins per target+field (decision 0009)."""
    return last_write_wins_fold(
        None,
        key_fn=field_update_key,
        version_fn=field_update_version,
    )


def fold_field_updates(
    records: Iterable[DatagramRecord],
) -> list[DatagramRecord]:
    """Return winning field-update facts (one per target+field)."""
    fold = field_updates_fold()
    return list(fold(list(records)))


def group_winners_by_target(
    winners: Iterable[DatagramRecord],
) -> dict[str, dict[str, str]]:
    """Map entity target → {field: value} from folded winners."""
    out: dict[str, dict[str, str]] = {}
    for rec in winners:
        bucket = out.setdefault(rec.target, {})
        bucket[rec.field] = rec.value
    return out


def apply_field_updates_to_mapping(
    base: dict[str, Any],
    records: Iterable[DatagramRecord],
) -> dict[str, Any]:
    """Pure hybrid-style merge: base entity mapping + ordered field facts.

    LWW per field by timestamp among ``records``; later timestamps win.
    """
    merged = dict(base)
    winners = fold_field_updates(records)
    for rec in winners:
        try:
            if rec.value.startswith("[") or rec.value.startswith("{"):
                val: Any = json.loads(rec.value)
            else:
                val = rec.value
            merged[rec.field] = val
        except Exception:
            merged[rec.field] = rec.value
    return merged


def record_is_newer_than_file(record: DatagramRecord, index_path: Path) -> bool:
    """True when this fact should replace the value stored in ``index_path``.

    A whole-file save newer than the datagram wins. The February remote
    journals must not clobber an ``_index.md`` written after them.
    """
    if not index_path.exists():
        return False
    stamp = _record_timestamp(record)
    if stamp is None:
        return False
    return stamp >= index_path.stat().st_mtime


def entity_markdown_path(data_root: Path, target: str) -> Optional[Path]:
    """The file compaction rewrites for ``target``.

    Companies use ``_index.md``. A person directory has one ``*.md`` whose
    name is the slugified person name, so that file is the snapshot.
    """
    entity_dir = data_root / target
    index_path = entity_dir / "_index.md"
    if index_path.is_file():
        return index_path
    if not entity_dir.is_dir():
        return None
    markdowns = sorted(path for path in entity_dir.glob("*.md") if path.is_file())
    if len(markdowns) == 1:
        return markdowns[0]
    if len(markdowns) > 1:
        logger.warning(
            "entity field compact: %s has %d markdown files; skipping apply",
            target,
            len(markdowns),
        )
    return None


def compact_entity_field_journal(
    *,
    wal_root: Optional[Path] = None,
    apply_to_entities: bool = True,
    data_root: Optional[Path] = None,
    compactor_id: Optional[str] = None,
    archive: bool = True,
) -> tuple[bool, int, int, list[Path]]:
    """Fold the entity field journal and write whole entity snapshots.

    1. Enumerate Shape A log via :class:`EntityFieldLogEdge` (stations LogEdge).
    2. Pure LWW fold per (target, field).
    3. If ``apply_to_entities``, merge winners that are newer than the entity
       file into that file (``_index.md``, or the person's single markdown).
    4. If ``archive``, retire a segment only when every record in it was
       eligible to apply. A segment that still holds an older fact stays put,
       so read-time fold can keep using it.

    Returns ``(did_work, record_count, entity_count, written_paths)``.
    ``record_count`` is the number of journal rows read, not the number
    applied. ``written_paths`` are the entity files this run rewrote.
    """
    edge = open_entity_field_log(wal_root=wal_root)
    root = edge._root()
    records = list(edge.iter_beyond())
    if not records:
        logger.info("entity field journal empty; nothing to compact")
        return False, 0, 0, []

    winners = fold_field_updates(records)
    cid = compactor_id or datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S")
    root_base = data_root if data_root is not None else paths.root
    written: list[Path] = []

    # Decide archive eligibility before the write, because the write updates
    # the file mtime and would make a just-applied fact look older than the file.
    archivable: list[Path] = []
    if archive:
        for wal_file in list(root.glob("*.usv")):
            if wal_file.name.startswith("checkpoint."):
                continue
            if _segment_is_fully_applied(wal_file, root_base):
                archivable.append(wal_file)
            else:
                logger.info(
                    "entity field journal left %s in place; it still holds an older fact",
                    wal_file.name,
                )

    if apply_to_entities:
        fresh: dict[str, dict[str, str]] = {}
        for rec in winners:
            entity_path = entity_markdown_path(root_base, rec.target)
            if entity_path is None or not record_is_newer_than_file(rec, entity_path):
                continue
            fresh.setdefault(rec.target, {})[rec.field] = rec.value
        for target, fields in fresh.items():
            applied = _apply_fields_to_entity_index(root_base, target, fields)
            if applied is not None:
                written.append(applied)

    moved = 0
    if archivable:
        archive_dir = root / "compacted" / cid
        archive_dir.mkdir(parents=True, exist_ok=True)
        for wal_file in archivable:
            dest = archive_dir / wal_file.name
            try:
                shutil.move(str(wal_file), str(dest))
                moved += 1
            except OSError as exc:
                logger.error("failed to archive journal segment %s: %s", wal_file, exc)

    logger.info(
        "entity field journal compacted id=%s records=%s winners=%s entities=%s segments=%s",
        cid,
        len(records),
        len(winners),
        len(written),
        moved,
    )
    return True, len(records), len(written), written


def _apply_fields_to_entity_index(
    data_root: Path, target: str, fields: dict[str, str]
) -> Optional[Path]:
    """Merge folded fields into the entity markdown file when it exists.

    A company snapshot is ``_index.md`` and keeps its description in the
    body. A person snapshot is the single ``*.md`` in the directory, and
    the markdown body after the frontmatter is left as it was. Returns
    the path written, or None when there is nothing to rewrite.
    """
    index_path = entity_markdown_path(data_root, target)
    if index_path is None:
        logger.warning(
            "entity field compact: no entity file for target %s; skipping apply",
            target,
        )
        return None

    try:
        content = index_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("cannot read %s: %s", index_path, exc)
        return None

    frontmatter: dict[str, Any] = {}
    body = ""
    if content.startswith("---") and "---" in content[3:]:
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                loaded = yaml.safe_load(parts[1])
                frontmatter = loaded if isinstance(loaded, dict) else {}
            except yaml.YAMLError as exc:
                logger.error("YAML error in %s: %s", index_path, exc)
                return None
            body = parts[2]
    else:
        body = content

    # fields are already LWW winners (string values from DatagramRecord)
    for key, raw in fields.items():
        try:
            if isinstance(raw, str) and (
                raw.startswith("[") or raw.startswith("{")
            ):
                frontmatter[key] = json.loads(raw)
            else:
                frontmatter[key] = raw
        except Exception:
            frontmatter[key] = raw

    is_company_index = index_path.name == "_index.md"
    description = frontmatter.pop("description", None) if is_company_index else None

    with open(index_path, "w", encoding="utf-8") as f:
        f.write("---\n")
        yaml.safe_dump(frontmatter, f, sort_keys=False)
        f.write("---\n")
        if is_company_index:
            if description:
                f.write(f"\n{description}\n")
            elif body.strip():
                f.write(body if body.startswith("\n") else f"\n{body.lstrip()}")
        else:
            f.write(body)

    logger.info("entity field compact applied %d fields to %s", len(fields), target)
    return index_path


def _record_timestamp(record: DatagramRecord) -> Optional[float]:
    try:
        stamp = datetime.fromisoformat(record.timestamp)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.timestamp()


def _segment_is_fully_applied(wal_file: Path, data_root: Path) -> bool:
    """A segment may be archived only when every row is newer than its file."""
    try:
        content = wal_file.read_text(encoding="utf-8")
    except OSError:
        return False
    saw_record = False
    for raw in content.split(RS):
        if not raw.strip():
            continue
        saw_record = True
        try:
            record = DatagramRecord.from_usv(raw)
        except (ValueError, IndexError):
            return False
        entity_path = entity_markdown_path(data_root, record.target)
        if entity_path is None or not record_is_newer_than_file(record, entity_path):
            return False
    return saw_record


def _period_day() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%d")


def _watermark_set(watermark: Optional[object]) -> set[str]:
    if watermark is None:
        return set()
    if isinstance(watermark, (list, set, tuple)):
        return {str(x) for x in watermark}
    if isinstance(watermark, str):
        return {watermark}
    return set()
