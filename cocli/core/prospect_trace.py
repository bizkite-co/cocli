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
from typing import Optional, Protocol

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
    results: dict[str, StationResult]


class StationCheck(Protocol):
    """A single station's identity-presence check, pre-indexed once."""

    name: str

    def check(self, identity: str) -> StationResult: ...


def trace_identity(checks: list[StationCheck], identity: str) -> dict[str, StationResult]:
    """Walk every given station for one identity."""
    return {c.name: c.check(identity) for c in checks}


def trace_identities(checks: list[StationCheck], identities: list[str]) -> list[TraceRow]:
    """Walk every given station for each identity - the group report."""
    return [TraceRow(identity=i, results=trace_identity(checks, i)) for i in identities]


class GmListResultsCheck:
    """Presence in a gm-list-shaped completed-results tree, indexed by the
    first field of each USV row (place_id for google_maps_prospects)."""

    name = "gm-list"

    def __init__(self, results_dir: Path) -> None:
        self._index: dict[str, list[str]] = {}
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

    def all_identities(self) -> set[str]:
        """Every place_id gm-list's *current* results tree still shows.
        Part of the seed set for a whole-campaign audit, alongside
        CheckpointPresenceCheck.all_identities() - gm-list alone is not
        sufficient (confirmed live 2026-08-18: gm-list's completed/results/
        tree doesn't retain every record forever, so some older checkpoint
        entries have no current gm-list file at all; IndexService.
        discover_all_place_ids() unions both)."""
        return set(self._index.keys())


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
        self._completed: set[str] = (
            {f.stem for f in completed_dir.glob("*.json")} if completed_dir.exists() else set()
        )
        self._pending: set[str] = set()
        if pending_dir.exists():
            for f in pending_dir.rglob("*"):
                if f.is_file() and not f.name.endswith(".lease"):
                    self._pending.add(f.stem if f.suffix else f.name)
        self._failed: set[str] = (
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
        self._ids: set[str] = set()
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

    def all_identities(self) -> set[str]:
        """Every identity present in the checkpoint - part of the seed set
        for a whole-campaign audit alongside GmListResultsCheck.all_identities().
        Confirmed live 2026-08-18: some checkpoint entries have no
        corresponding *current* gm-list result file (older/legacy records -
        gm-list's completed/results/ tree doesn't retain everything forever),
        so seeding a campaign audit from gm-list alone silently excludes
        them and understates real coverage."""
        return set(self._ids)


class ProspectDomainIndex:
    """place_id -> domain lookup, built once from the checkpoint file plus
    any not-yet-compacted WAL shards on this machine.

    Needed for the enrichment hop specifically: per
    docs/_schema/traceability.md, enrichment's identity key is the prospect's
    *domain*, not its place_id (multiple place_ids can share a domain, and a
    place_id has no domain until gm-details finds one) - so unlike every
    other station here, checking enrichment for a given business requires
    first resolving place_id -> domain through this index, then checking the
    domain against the enrichment queue.

    Uses USVDictReader with explicit fieldnames from GoogleMapsProspect's own
    field order, matching to_usv()'s serialization exactly - these files are
    headerless (CLAUDE.md: "Sharded .usv files (headerless...)"), so passing
    no fieldnames (as GoogleMapsProspect.get_by_place_id does) misreads the
    first real data row as a header and effectively breaks lookups; a
    separate, pre-existing bug this class deliberately does not repeat.
    """

    def __init__(self, checkpoint_path: Path, wal_root: Optional[Path] = None) -> None:
        from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
        from cocli.utils.usv_utils import USVDictReader

        fieldnames = list(GoogleMapsProspect.model_fields.keys())
        self._rows: dict[str, dict[str, str]] = {}

        if checkpoint_path.exists():
            try:
                with open(checkpoint_path, "r", encoding="utf-8", errors="replace") as f:
                    reader = USVDictReader(f, fieldnames=fieldnames)
                    for row in reader:
                        place_id = row.get("place_id")
                        if place_id and row.get("domain"):
                            self._rows[place_id] = row
            except OSError:
                pass

        if wal_root is not None and wal_root.exists():
            for wal_file in wal_root.rglob("*.usv"):
                place_id = wal_file.stem
                if place_id in self._rows:
                    continue  # checkpoint (compacted, authoritative) wins
                try:
                    text = wal_file.read_text(errors="replace")
                except OSError:
                    continue
                with_header = [fieldnames] + [
                    line.split(US) for line in text.split("\n") if line.strip()
                ]
                if len(with_header) < 2:
                    continue
                row = dict(zip(fieldnames, with_header[1]))
                if row.get("domain"):
                    self._rows[place_id] = row

    def get_domain(self, place_id: str) -> Optional[str]:
        row = self._rows.get(place_id)
        return row.get("domain") if row else None

    def get_slug(self, place_id: str) -> Optional[str]:
        """Company slug for a place_id already known to have a domain
        (get_domain returned non-None) - needed to construct a valid
        EnrichmentTask (company_slug is a required field)."""
        row = self._rows.get(place_id)
        if not row:
            return None
        return row.get("slug") or None


class PrebuiltSetCheck:
    """Presence in a pre-built identity set - for any station whose contents
    can only be gathered by an out-of-process step (e.g. SSH-listing a Pi
    node's WAL directory). The set is built by the caller; this class has no
    knowledge of how, keeping it free of any services/-layer dependency."""

    def __init__(self, name: str, ids: set[str]) -> None:
        self.name = name
        self._ids = ids

    def check(self, identity: str) -> StationResult:
        state = "present" if identity in self._ids else "absent"
        return StationResult(station=self.name, state=state)


# gm-list raw result column order (matches
# cocli.core.transformers.gm_list_to_checkpoint._load_gm_list_results_auto -
# keep in sync with that if the gm-list result shape ever changes).
_GM_LIST_COLUMNS = [
    "place_id", "company_slug", "name", "category", "phone", "domain",
    "reviews_count", "average_rating", "street_address", "gmb_url",
    "discovery_phrase", "discovery_tile_id", "html",
]


def find_gm_list_rows(results_dir: Path, place_ids: set[str]) -> dict[str, dict[str, str]]:
    """Targeted lookup of full gm-list result rows for a specific, small set
    of place_ids - deliberately not a full-index build like
    GmListResultsCheck (which stays presence-only/lightweight, since it
    typically covers far more rows than any single lookup needs). Used by
    the requeue-stuck-details tool to reconstruct enough of a GmItemTask to
    re-enqueue a stuck detail scrape, without caching every scraped item's
    full row (including html) in memory the way a full index would.

    Returns place_id -> {column_name: value}, only for place_ids actually
    found. If the same place_id appears in multiple result files (the same
    business found via overlapping tiles/queries), the first one
    encountered wins - the reconstructed fields are scrape hints for a
    fresh re-scrape, not a source of truth, so picking a specific "best"
    duplicate isn't required here.
    """
    found: dict[str, dict[str, str]] = {}
    if not place_ids or not results_dir.exists():
        return found
    remaining = set(place_ids)
    for f in results_dir.rglob("*.usv"):
        if not remaining:
            break
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        for line in text.split("\n"):
            if not remaining:
                break
            if not line.strip():
                continue
            fields = line.split(US)
            identity = fields[0] if fields else ""
            if identity in remaining:
                found[identity] = {
                    col: (fields[i] if i < len(fields) else "")
                    for i, col in enumerate(_GM_LIST_COLUMNS)
                }
                remaining.discard(identity)
    return found


def diagnose_prospect_trace(
    results: dict[str, StationResult], enrichment: Optional[StationResult] = None
) -> str:
    """google_maps_prospects-specific interpretation of a combined trace.

    Station names expected: gm-list, gm-details, pi-wal, checkpoint (see
    IndexService.trace_prospects, which assembles these four checks). This
    verdict logic is workflow-shaped, not generic - a second workflow with a
    different station sequence would need its own diagnose_* function; only
    the walking mechanism above is meant to be reusable as-is.

    `enrichment` is optional and separate from `results` because it's keyed
    by domain, not place_id (see ProspectDomainIndex) - the caller resolves
    the domain and runs that check itself, then passes the result in here
    only once the record has cleared checkpoint (no point reporting an
    enrichment gap for a record that's not even reliably in the checkpoint
    yet - that's a more fundamental problem and gets reported first).
    """
    checkpoint = results.get("checkpoint")
    wal = results.get("pi-wal")
    gm_details = results.get("gm-details")
    gm_list = results.get("gm-list")

    if checkpoint is not None and checkpoint.state == "present":
        if enrichment is None:
            return "present in current checkpoint"
        if enrichment.state == "no domain":
            return "present in checkpoint, no domain found yet - can't enrich"
        if enrichment.state == "completed":
            return "present in checkpoint, enrichment completed"
        if enrichment.state in ("pending", "failed"):
            return f"present in checkpoint, enrichment {enrichment.state}"
        return "present in checkpoint, never reached enrichment queue - enrichment-enqueue gap"
    if wal is not None and wal.state == "present":
        return "WAL has it but the fold didn't include it - FOLD BUG"
    if gm_details is not None and gm_details.state == "completed":
        return "gm-details completed but never reached WAL - WAL-write or sync gap"
    if gm_list is not None and gm_list.state == "found" and gm_details is not None and gm_details.state != "completed":
        return f"rediscovered by gm-list but gm-details status={gm_details.state} - detailing gap"
    if gm_list is not None and gm_list.state == "absent":
        return "never rediscovered by gm-list - upstream/query gap"
    return "unclear - needs manual look"


# Maps a diagnose_prospect_trace() verdict prefix to one of the three named
# gap categories from docs/_schema/traceability.md's Section 3, for
# aggregate reporting (cocli audit campaign). Order matters - first prefix
# match wins.
GAP_CATEGORY_BY_VERDICT_PREFIX: list[tuple[str, str]] = [
    ("present in checkpoint, enrichment completed", "no gap"),
    ("present in current checkpoint", "no gap"),
    ("present in checkpoint, no domain found yet", "no gap (pre-enrichment)"),
    ("present in checkpoint, enrichment pending", "no gap (enrichment in flight)"),
    ("present in checkpoint, enrichment failed", "Integrity Gap (enrichment failed)"),
    ("present in checkpoint, never reached enrichment queue", "Identity Gap (enrichment-enqueue)"),
    ("WAL has it but the fold didn't include it", "Consensus Gap (fold bug)"),
    ("gm-details completed but never reached WAL", "Identity Gap (WAL-write/sync)"),
    ("rediscovered by gm-list but gm-details status", "Identity Gap (detailing)"),
    ("never rediscovered by gm-list", "Identity Gap (upstream/query)"),
]


def categorize_verdict(verdict: str) -> str:
    """Aggregate-reporting category for a single verdict string - see
    GAP_CATEGORY_BY_VERDICT_PREFIX."""
    for prefix, category in GAP_CATEGORY_BY_VERDICT_PREFIX:
        if verdict.startswith(prefix):
            return category
    return "unclassified - needs manual look"
