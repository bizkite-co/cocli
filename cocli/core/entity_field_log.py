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
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

import yaml
from stations.backends import LocalPathBackend
from stations.compactor import last_write_wins_fold
from stations.station import StationDecl

from cocli.core.paths import paths
from cocli.models.wal.record import RS, DatagramRecord

logger = logging.getLogger(__name__)


def _station() -> StationDecl[DatagramRecord]:
    return StationDecl(
        name="entity-field-journal",
        path_template="wal/{period}_{writer}.usv",
        model=DatagramRecord,
        serialization="usv-segment",
    )


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
) -> List[DatagramRecord]:
    """Return winning field-update facts (one per target+field)."""
    fold = field_updates_fold()
    return list(fold(list(records)))


def group_winners_by_target(
    winners: Iterable[DatagramRecord],
) -> Dict[str, Dict[str, str]]:
    """Map entity target → {field: value} from folded winners."""
    out: Dict[str, Dict[str, str]] = {}
    for rec in winners:
        bucket = out.setdefault(rec.target, {})
        bucket[rec.field] = rec.value
    return out


def apply_field_updates_to_mapping(
    base: Dict[str, Any],
    records: Iterable[DatagramRecord],
) -> Dict[str, Any]:
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


def compact_entity_field_journal(
    *,
    wal_root: Optional[Path] = None,
    apply_to_entities: bool = True,
    data_root: Optional[Path] = None,
    compactor_id: Optional[str] = None,
) -> Tuple[bool, int, int]:
    """Fold the entity field journal and write whole entity snapshots.

    1. Enumerate Shape A log via :class:`EntityFieldLogEdge` (stations LogEdge).
    2. Pure LWW fold per (target, field).
    3. If ``apply_to_entities``, merge winners into each entity's ``_index.md``
       (compaction updates the **whole** entity file — not in-place field surgery
       as the multi-writer protocol).
    4. Retire consumed journal segments (move to ``wal/compacted/{run_id}/``).

    Returns ``(did_work, record_count, entity_count)``.
    """
    edge = open_entity_field_log(wal_root=wal_root)
    root = edge._root()
    records = list(edge.iter_beyond())
    if not records:
        logger.info("entity field journal empty; nothing to compact")
        return False, 0, 0

    winners = fold_field_updates(records)
    by_target = group_winners_by_target(winners)
    cid = compactor_id or datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S")
    entities_touched = 0

    if apply_to_entities:
        root_base = data_root if data_root is not None else paths.root
        for target, fields in by_target.items():
            if _apply_fields_to_entity_index(root_base, target, fields):
                entities_touched += 1

    # Retire Shape A segments that participated (all non-checkpoint *.usv)
    archive = root / "compacted" / cid
    archive.mkdir(parents=True, exist_ok=True)
    moved = 0
    for wal_file in list(root.glob("*.usv")):
        if wal_file.name.startswith("checkpoint."):
            continue
        dest = archive / wal_file.name
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
        entities_touched,
        moved,
    )
    return True, len(records), entities_touched


def _apply_fields_to_entity_index(
    data_root: Path, target: str, fields: Dict[str, str]
) -> bool:
    """Merge folded fields into ``{data_root}/{target}/_index.md`` if present.

    Writes a whole ``_index.md`` (YAML frontmatter + body). Multi-writer
    coordination stays on the log; this is the single-writer compact step.
    """
    entity_dir = data_root / target
    index_path = entity_dir / "_index.md"
    if not index_path.exists():
        logger.warning(
            "entity field compact: no _index.md for target %s; skipping apply",
            target,
        )
        return False

    try:
        content = index_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("cannot read %s: %s", index_path, exc)
        return False

    frontmatter: Dict[str, Any] = {}
    body = ""
    if content.startswith("---") and "---" in content[3:]:
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                loaded = yaml.safe_load(parts[1])
                frontmatter = loaded if isinstance(loaded, dict) else {}
            except yaml.YAMLError as exc:
                logger.error("YAML error in %s: %s", index_path, exc)
                return False
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

    description = frontmatter.pop("description", None)

    with open(index_path, "w", encoding="utf-8") as f:
        f.write("---\n")
        yaml.safe_dump(frontmatter, f, sort_keys=False)
        f.write("---\n")
        if description:
            f.write(f"\n{description}\n")
        elif body.strip():
            f.write(body if body.startswith("\n") else f"\n{body.lstrip()}")

    logger.info("entity field compact applied %d fields to %s", len(fields), target)
    return True


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
