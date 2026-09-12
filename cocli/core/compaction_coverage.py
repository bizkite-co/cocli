"""Runtime coverage report for compaction runs.

Declares which stations a compaction is supposed to read, then prints
what this run actually pulled vs what sits on disk unread. That is how
gm-list -> prospects going dark for a month would have shown up without
tracing code (compaction-sourcestation-coverage-manifest).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeclaredSource:
    source_id: str
    relpath: str
    label: str = ""

    @property
    def display(self) -> str:
        return self.label or self.relpath


# Compaction name -> stations that MUST be considered each run.
# A source with files on disk and 0 records_read is the gap signal.
COMPACTION_DECLARED_SOURCES: dict[str, tuple[DeclaredSource, ...]] = {
    "google_maps_prospects": (
        DeclaredSource(
            "prospects-wal",
            "indexes/google_maps_prospects/wal",
            "indexes/google_maps_prospects/wal/",
        ),
        DeclaredSource(
            "gm-list-results",
            "queues/gm-list/completed/results",
            "queues/gm-list/completed/results/",
        ),
    ),
    "gm-list": (
        DeclaredSource(
            "gm-list-results",
            "queues/gm-list/completed/results",
            "queues/gm-list/completed/results/",
        ),
    ),
    "email-index": (
        DeclaredSource(
            "email-inbox",
            "indexes/emails/inbox",
            "indexes/emails/inbox/",
        ),
        DeclaredSource(
            "email-shards",
            "indexes/emails/shards",
            "indexes/emails/shards/",
        ),
    ),
}


def count_usv_records(root: Path) -> int:
    """Non-empty USV lines under ``root`` (file or directory)."""
    if not root.exists():
        return 0
    if root.is_file():
        return _count_usv_file(root)
    total = 0
    for path in root.rglob("*.usv"):
        total += _count_usv_file(path)
    return total


def _count_usv_file(path: Path) -> int:
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            return sum(1 for line in handle if line.strip())
    except OSError:
        return 0


@dataclass
class CompactionCoverage:
    compaction: str
    campaign: str
    run_id: str
    campaign_dir: Path
    records_read: dict[str, int] = field(default_factory=dict)

    def record_read(self, source_id: str, records: int) -> None:
        self.records_read[source_id] = self.records_read.get(source_id, 0) + records

    def format_human(self) -> str:
        declared = COMPACTION_DECLARED_SOURCES.get(self.compaction, ())
        declared_ids = {src.source_id for src in declared}
        read_rows: list[tuple[str, int]] = []
        unread_rows: list[tuple[str, int]] = []

        for src in declared:
            available = count_usv_records(self.campaign_dir / src.relpath)
            read = self.records_read.get(src.source_id, 0)
            if read > 0:
                read_rows.append((src.display, read))
            elif available > 0:
                unread_rows.append((src.display, available))

        for source_id, read in self.records_read.items():
            if source_id not in declared_ids and read > 0:
                read_rows.append((source_id, read))

        lines = [
            f"Compaction: {self.compaction} ({self.campaign}), {self.run_id}",
            "Sources read:",
        ]
        if read_rows:
            width = max(len(name) for name, _ in read_rows)
            for name, n in read_rows:
                lines.append(f"  {name.ljust(width)}  {n:>8} records")
        else:
            lines.append("  (none)")
        lines.append("Sources NOT read (exist on disk, not part of this run):")
        if unread_rows:
            width = max(len(name) for name, _ in unread_rows)
            for name, n in unread_rows:
                lines.append(f"  {name.ljust(width)}  {n:>8} records available")
        else:
            lines.append("  (none)")
        return "\n".join(lines)

    def emit(self, *, log_file: Path | None = None) -> str:
        text = self.format_human()
        logger.info("compaction coverage\n%s", text)
        if log_file is not None:
            try:
                log_file.parent.mkdir(parents=True, exist_ok=True)
                with log_file.open("a", encoding="utf-8") as handle:
                    handle.write(
                        f"\n# coverage {datetime.now(timezone.utc).isoformat()}\n"
                    )
                    handle.write(text)
                    handle.write("\n")
            except OSError as exc:
                logger.debug("could not append coverage to %s: %s", log_file, exc)
        return text


def coverage_for(
    compaction: str,
    campaign: str,
    campaign_dir: Path,
    *,
    run_id: str | None = None,
    records_read: Mapping[str, int] | None = None,
) -> CompactionCoverage:
    rid = run_id or f"run_{int(datetime.now(timezone.utc).timestamp())}"
    cov = CompactionCoverage(
        compaction=compaction,
        campaign=campaign,
        run_id=rid,
        campaign_dir=campaign_dir,
    )
    if records_read:
        for source_id, n in records_read.items():
            cov.record_read(source_id, n)
    return cov
