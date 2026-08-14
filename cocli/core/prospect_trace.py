"""Trace one identity (or a batch of identities) through the stations a
pipeline touches, reporting presence/state at each one.

Split out of a production incident (2026-08-13): turboship's
google_maps_prospects compaction got fixed, but the "valid customer" export
count still dropped after a fresh compaction. Diagnosing why required
manually tracing individual place_ids across every station the pipeline
touches - no existing tool did that. `stations inspect` (see
~/repos/stations) is aggregate/structural only: per-station item counts and
lease health, with no notion of a record identity at all. This module is the
identity-scoped complement cocli needs today, deliberately built so a future
stations-level capability (task-agent ticket, stations repo:
identity-trace-capability-given-a-workflow-item-id-walk-all-declared-stations-and-report-presencestate)
can absorb it later without cocli needing a second implementation - the
station-check shape here (pre-index once, O(1) lookup per identity) is the
same shape that capability is meant to generalize.

Each StationCheck indexes its station exactly once at construction, then
answers per-identity lookups in O(1). That indexing discipline is the whole
point: the mistake this replaces is grep/find-per-identity, which does not
scale past a handful of records.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Set

US = "\x1f"


@dataclass
class StationResult:
    """One station's answer to "do you have this identity, and in what state."""

    station: str
    state: str
    detail: str = ""


@dataclass
class TraceRow:
    identity: str
    results: Dict[str, StationResult]


class StationCheck(Protocol):
    """A single station's identity-presence check, pre-indexed once."""

    name: str

    def check(self, identity: str) -> StationResult: ...


def trace_identity(checks: List[StationCheck], identity: str) -> Dict[str, StationResult]:
    """Walk every given station for one identity."""
    return {c.name: c.check(identity) for c in checks}


def trace_identities(checks: List[StationCheck], identities: List[str]) -> List[TraceRow]:
    """Walk every given station for each identity - the group report."""
    return [TraceRow(identity=i, results=trace_identity(checks, i)) for i in identities]


class GmListResultsCheck:
    """Presence in a gm-list-shaped completed-results tree, indexed by the
    first field of each USV row (place_id for google_maps_prospects)."""

    name = "gm-list"

    def __init__(self, results_dir: Path) -> None:
        self._index: Dict[str, List[str]] = {}
        if not results_dir.exists():
            return
        for f in results_dir.rglob("*.usv"):
            try:
                text = f.read_text(errors="replace")
            except OSError:
                continue
            rel = str(f.relative_to(results_dir))
            for line in text.split("\n"):
                if not line.strip():
                    continue
                identity = line.split(US, 1)[0]
                if identity:
                    self._index.setdefault(identity, []).append(rel)

    def check(self, identity: str) -> StationResult:
        hits = self._index.get(identity, [])
        if not hits:
            return StationResult(station=self.name, state="absent")
        return StationResult(
            station=self.name,
            state="found",
            detail=f"{len(hits)} hit(s); latest {hits[-1]}",
        )


class QueueBucketCheck:
    """Presence of an identity as a file stem across a queue's
    completed/pending/failed buckets - the filename-is-the-identity station
    shape, e.g. gm-details/completed/{place_id}.json."""

    def __init__(
        self,
        name: str,
        completed_dir: Path,
        pending_dir: Path,
        failed_dir: Optional[Path] = None,
    ) -> None:
        self.name = name
        self._completed: Set[str] = (
            {f.stem for f in completed_dir.glob("*.json")} if completed_dir.exists() else set()
        )
        self._pending: Set[str] = set()
        if pending_dir.exists():
            for f in pending_dir.rglob("*"):
                if f.is_file() and not f.name.endswith(".lease"):
                    self._pending.add(f.stem if f.suffix else f.name)
        self._failed: Set[str] = (
            {f.stem for f in failed_dir.glob("*.json")}
            if failed_dir is not None and failed_dir.exists()
            else set()
        )

    def check(self, identity: str) -> StationResult:
        if identity in self._completed:
            return StationResult(station=self.name, state="completed")
        if identity in self._pending:
            return StationResult(station=self.name, state="pending")
        if identity in self._failed:
            return StationResult(station=self.name, state="failed")
        return StationResult(station=self.name, state="never seen")


class CheckpointPresenceCheck:
    """Presence in a checkpoint-shaped index file (first field of each USV
    row is the identity)."""

    name = "checkpoint"

    def __init__(self, checkpoint_path: Path) -> None:
        self._ids: Set[str] = set()
        if not checkpoint_path.exists():
            return
        with open(checkpoint_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                identity = line.split(US, 1)[0]
                if identity:
                    self._ids.add(identity)

    def check(self, identity: str) -> StationResult:
        state = "present" if identity in self._ids else "absent"
        return StationResult(station=self.name, state=state)


class PrebuiltSetCheck:
    """Presence in a pre-built identity set - for any station whose contents
    can only be gathered by an out-of-process step (e.g. SSH-listing a Pi
    node's WAL directory). The set is built by the caller; this class has no
    knowledge of how, keeping it free of any services/-layer dependency."""

    def __init__(self, name: str, ids: Set[str]) -> None:
        self.name = name
        self._ids = ids

    def check(self, identity: str) -> StationResult:
        state = "present" if identity in self._ids else "absent"
        return StationResult(station=self.name, state=state)


def diagnose_prospect_trace(results: Dict[str, StationResult]) -> str:
    """google_maps_prospects-specific interpretation of a combined trace.

    Station names expected: gm-list, gm-details, pi-wal, checkpoint (see
    IndexService.trace_prospects, which assembles these four checks). This
    verdict logic is workflow-shaped, not generic - a second workflow with a
    different station sequence would need its own diagnose_* function; only
    the walking mechanism above is meant to be reusable as-is.
    """
    checkpoint = results.get("checkpoint")
    wal = results.get("pi-wal")
    gm_details = results.get("gm-details")
    gm_list = results.get("gm-list")

    if checkpoint is not None and checkpoint.state == "present":
        return "present in current checkpoint"
    if wal is not None and wal.state == "present":
        return "WAL has it but the fold didn't include it - FOLD BUG"
    if gm_details is not None and gm_details.state == "completed":
        return "gm-details completed but never reached WAL - WAL-write or sync gap"
    if gm_list is not None and gm_list.state == "found" and gm_details is not None and gm_details.state != "completed":
        return f"rediscovered by gm-list but gm-details status={gm_details.state} - enrichment gap"
    if gm_list is not None and gm_list.state == "absent":
        return "never rediscovered by gm-list - upstream/query gap"
    return "unclear - needs manual look"
