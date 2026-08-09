"""Generic identity-set reconciliation between two directory trees of task files.

Diffs two queue-shaped directories (`{shard}/{lat}/{lon}/{phrase}.usv`-style)
by normalized identity, ignoring the leading shard-bucket segment - sharding
is a storage-layout detail, not part of a record's identity, so two write
sites for "the same" record aren't required to agree on it structurally.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .task_file_filter import is_valid_task_data_file


@dataclass(frozen=True)
class ReconciliationResult:
    left_total: int
    right_total: int
    left_only: frozenset[str]
    right_only: frozenset[str]
    intersection: frozenset[str]

    @property
    def matched(self) -> int:
        return len(self.intersection)


def _identities(root: Path, *, strip_leading_segments: int) -> frozenset[str]:
    if not root.exists():
        return frozenset()
    ids: set[str] = set()
    for f in root.rglob("*"):
        if not f.is_file() or not is_valid_task_data_file(f.name):
            continue
        parts = f.relative_to(root).with_suffix("").parts
        ids.add("/".join(parts[strip_leading_segments:]))
    return frozenset(ids)


def reconcile_identities(
    left_root: Path,
    right_root: Path,
    *,
    strip_leading_segments: int = 1,
) -> ReconciliationResult:
    """Diff two directory trees of task/result files by normalized identity.

    Identity is the relative path with its extension stripped and the first
    `strip_leading_segments` path components removed (default 1, to drop a
    leading shard-bucket digit). Bookkeeping files (lease/attempts sidecars,
    datapackage.json, schema_ledger.json, mission.usv) are excluded via
    `is_valid_task_data_file`, so raw counts aren't inflated by them.
    """
    left = _identities(left_root, strip_leading_segments=strip_leading_segments)
    right = _identities(right_root, strip_leading_segments=strip_leading_segments)
    return ReconciliationResult(
        left_total=len(left),
        right_total=len(right),
        left_only=left - right,
        right_only=right - left,
        intersection=left & right,
    )
