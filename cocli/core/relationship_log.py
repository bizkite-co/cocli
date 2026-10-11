"""Stations LogEdge for the relationship journal (ADR-014).

Retained Shape A segments under ``wal/relationships/``. Append and iterate
only. Compaction that publishes ``org.md`` is a later slice and must not
delete these segments.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from stations.backends import LocalPathBackend
from stations.compactor import last_write_wins_fold

from cocli.core.paths import paths
from cocli.models.wal.relationship import RelationshipRecord
from cocli.station_defs.wal.relationship import RELATIONSHIP_JOURNAL

logger = logging.getLogger(__name__)


def _station() -> Any:
    return RELATIONSHIP_JOURNAL


def relationship_instance_key(record: RelationshipRecord) -> str:
    """LWW identity for org and membership facts: one winner per id."""
    return record.relationship_id


def observation_key(record: RelationshipRecord) -> str:
    """LWW identity for a single-valued observation such as email provider.

    The object is not part of the key, so a newer gateway replaces the older
    one. Distinct relationship ids for the same subject and predicate collapse.
    """
    return f"{record.subject_type}\x1f{record.subject}\x1f{record.predicate}"


def observation_member_key(record: RelationshipRecord) -> str:
    """LWW identity for one member of a set, such as one product in a stack.

    A second product is a different key and survives. A later row for the same
    product replaces the earlier row.
    """
    return (
        f"{record.subject_type}\x1f{record.subject}\x1f"
        f"{record.predicate}\x1f{record.object_key}"
    )


def relationship_version(record: RelationshipRecord) -> str:
    return record.timestamp


def fold_relationship_instances(
    records: Iterable[RelationshipRecord],
) -> list[RelationshipRecord]:
    """One winning row per ``relationship_id``."""
    fold = last_write_wins_fold(
        None,
        key_fn=relationship_instance_key,
        version_fn=relationship_version,
    )
    return list(fold(list(records)))


def fold_observations(
    records: Iterable[RelationshipRecord],
) -> list[RelationshipRecord]:
    """One winning row per subject and predicate (single-valued)."""
    fold = last_write_wins_fold(
        None,
        key_fn=observation_key,
        version_fn=relationship_version,
    )
    return list(fold(list(records)))


def fold_observation_members(
    records: Iterable[RelationshipRecord],
) -> list[RelationshipRecord]:
    """One winning row per subject, predicate, and object."""
    fold = last_write_wins_fold(
        None,
        key_fn=observation_member_key,
        version_fn=relationship_version,
    )
    return list(fold(list(records)))


@dataclass
class RelationshipLogEdge:
    """``LogEdge[RelationshipRecord]`` over the retained relationship journal."""

    station: Any = field(default_factory=_station)
    backend: Any = field(default_factory=LocalPathBackend)
    wal_root: Optional[Path] = None

    def _root(self) -> Path:
        if self.wal_root is not None:
            return self.wal_root
        return Path(paths.wal.path) / "relationships"

    def append(self, record: RelationshipRecord) -> str:
        """Append-only write into the node's Shape A segment (P7)."""
        root = self._root()
        root.mkdir(parents=True, exist_ok=True)
        segment = root / f"{_period_day()}_{record.node_id}.usv"
        with open(segment, "a", encoding="utf-8") as handle:
            handle.write(record.to_usv())
        logger.info(
            "relationship log append: %s %s %s in %s",
            record.subject,
            record.predicate,
            record.object_key,
            segment,
        )
        return segment.name

    def iter_beyond(
        self, watermark: Optional[object] = None
    ) -> Iterator[RelationshipRecord]:
        """Yield facts. ``watermark`` is a segment filename or filenames to skip."""
        root = self._root()
        if not root.exists():
            return
        seen = _watermark_set(watermark)
        for wal_file in sorted(root.glob("*.usv")):
            if wal_file.name in seen or str(wal_file) in seen:
                continue
            if wal_file.name.startswith("checkpoint."):
                continue
            try:
                content = wal_file.read_text(encoding="utf-8")
            except OSError as exc:
                logger.error("cannot read relationship segment %s: %s", wal_file, exc)
                continue
            for line in content.splitlines():
                if not line.strip():
                    continue
                yield RelationshipRecord.from_usv(line)


def open_relationship_log(
    *, wal_root: Optional[Path] = None
) -> RelationshipLogEdge:
    """Return a stations-conforming LogEdge for the relationship journal."""
    return RelationshipLogEdge(wal_root=wal_root)


def _period_day() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%d")


def _watermark_set(watermark: Optional[object]) -> set[str]:
    if watermark is None:
        return set()
    if isinstance(watermark, (list, set, tuple)):
        return {str(item) for item in watermark}
    if isinstance(watermark, str):
        return {watermark}
    return set()
