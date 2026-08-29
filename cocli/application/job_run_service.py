"""Persistence and lifecycle for ScrapeJobRun - the explicit trigger for
enqueuing new work into gm-list/pending/ (see
cocli/models/campaigns/scrape_job_run.py for the full design rationale).

Caller-agnostic by design: create_job_run()/mark_discovery_gen_completed()
don't care whether they're invoked from fresh discovery-gen generation
(cocli dev process-map-tile) or a future requeue process reusing existing
discovery-gen data - both are equally valid ways to create a run. Only an
explicit call to create_job_run() can ever cause gm-list/pending/ to be
topped up; draining to zero is never itself a trigger.
"""

from __future__ import annotations

import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import List, Optional

from ..core.paths import paths
from ..core.queue.reconcile import identities_with_paths
from ..models.campaigns.scrape_job_run import ScrapeJobRun


def _index_path(campaign_name: str) -> Path:
    return paths.campaign(campaign_name).job_runs / "job-runs.usv"


def _run_dir(campaign_name: str, run_id: str) -> Path:
    return paths.campaign(campaign_name).job_runs / run_id


def _metadata_path(campaign_name: str, run_id: str) -> Path:
    return _run_dir(campaign_name, run_id) / "metadata.json"


def _identities_path(campaign_name: str, run_id: str) -> Path:
    return _run_dir(campaign_name, run_id) / "identities.usv"


def _load_index(campaign_name: str) -> List[ScrapeJobRun]:
    index_path = _index_path(campaign_name)
    if not index_path.exists():
        return []
    runs: List[ScrapeJobRun] = []
    with open(index_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                runs.append(ScrapeJobRun.from_usv(line))
    return runs


def _save_index(campaign_name: str, runs: List[ScrapeJobRun]) -> None:
    ScrapeJobRun.save_usv_with_datapackage(
        runs, _index_path(campaign_name), resource_name="job-runs"
    )


def _persist(run: ScrapeJobRun) -> None:
    """Writes the per-run JSON metadata and upserts the campaign-wide
    index row (same model, two representations - see ScrapeJobRun's
    docstring)."""
    metadata_path = _metadata_path(run.campaign_name, run.id)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(run.model_dump_json(indent=2), encoding="utf-8")

    runs = _load_index(run.campaign_name)
    for i, existing in enumerate(runs):
        if existing.id == run.id:
            runs[i] = run
            break
    else:
        runs.append(run)
    _save_index(run.campaign_name, runs)


def create_job_run(campaign_name: str, *, hostname: Optional[str] = None) -> ScrapeJobRun:
    """Creates a new job run. This is the only thing that can ever cause
    new work to land in gm-list/pending/ - see ScrapeJobRun's docstring.
    Caller-agnostic: doesn't care whether the caller is fresh discovery-gen
    generation or a future requeue process reusing existing discovery-gen
    data.
    """
    host = hostname or socket.gethostname()
    now = datetime.now(UTC)
    # Microsecond precision, not just seconds - two runs created on the
    # same machine within the same wall-clock second (easily happens,
    # not just a theoretical race) would otherwise collide on id and
    # silently overwrite each other's index row in _persist().
    run_id = f"{now.strftime('%Y%m%dT%H%M%S%f')}Z_{host}"
    run = ScrapeJobRun(id=run_id, campaign_name=campaign_name, created_at=now)
    _persist(run)
    return run


def mark_discovery_gen_completed(run: ScrapeJobRun, identities: List[str]) -> ScrapeJobRun:
    """Snapshots this run's identity set and marks it ready to be copied
    into gm-list/pending/. `identities` is entirely caller-provided - this
    function doesn't inspect discovery-gen itself, so the caller decides
    what belongs to the run (freshly generated tiles, or an existing set
    selected for a requeue).
    """
    unique_sorted = sorted(set(identities))
    ids_path = _identities_path(run.campaign_name, run.id)
    ids_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ids_path, "w", encoding="utf-8") as f:
        for identity in unique_sorted:
            f.write(identity + "\n")

    updated = run.model_copy(
        update={
            "discovery_gen_completed_at": datetime.now(UTC),
            "identity_count": len(unique_sorted),
        }
    )
    _persist(updated)
    return updated


def load_identities(run: ScrapeJobRun) -> List[str]:
    ids_path = _identities_path(run.campaign_name, run.id)
    if not ids_path.exists():
        return []
    return [
        line.strip()
        for line in ids_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def enqueue_gm_list_for_run(run: ScrapeJobRun, *, rescrape_all: bool = False) -> ScrapeJobRun:
    """Copies this run's snapshotted identities into gm-list/pending/,
    scoped to exactly this run (not the whole discovery-gen/completed
    tree) - reuses the existing dedup/reconcile logic in
    gm_list_enqueue_service.py so an item already gm-list-completed still
    gets skipped even within this run's own scope (unless rescrape_all).
    Idempotent - safe for the resilience poller to call again on a run
    that already has started_at unset because a prior attempt was
    interrupted mid-copy. Sets started_at unconditionally on success
    (copied==0 is a valid outcome if every identity in scope already
    resolved by the time this ran), regardless of how many items
    actually needed copying.

    rescrape_all: bypass the already-completed filter - every identity in
    scope gets copied regardless of whether it already has a gm-list
    receipt. Needed for requeue_job_run(): re-scraping a previous run's
    already-fully-resolved identities would otherwise copy zero items
    (they all trivially "already have a receipt"), and the new run would
    look done without ever re-scraping anything.
    """
    from .gm_list_enqueue_service import enqueue_unscraped_to_gm_list_pending

    identities = load_identities(run)
    enqueue_unscraped_to_gm_list_pending(
        campaign_name=run.campaign_name,
        identity_scope=frozenset(identities),
        dry_run=False,
        rescrape_all=rescrape_all,
    )
    updated = run.model_copy(update={"started_at": datetime.now(UTC)})
    _persist(updated)
    return updated


def check_and_mark_gm_list_completed(run: ScrapeJobRun) -> bool:
    """True (and persists gm_list_completed_at) once every identity in
    this run's snapshot has reached completed-or-failed in gm-list - not
    100% success, since real scraping always has some failure rate.

    Known gap: gm-list's dead-letter path is suspected broken (see
    task-agent ticket
    gm-list-dead-letter-path-likely-broken-dead-letter-assumes-task-idtask.json-shape-gm-list-is-flat-.usv-files)
    so only completed receipts are checked here, not failed/ - a run with
    a perpetually-erroring identity won't complete until that's fixed.
    """
    from typing import cast

    from ..core.queue.factory import get_queue_manager
    from ..core.queue.filesystem import FilesystemGmListQueue

    identities = set(load_identities(run))
    if not identities:
        return False

    # queue_type="gm-list" always resolves to FilesystemGmListQueue for the
    # filesystem provider; CampaignQueueProtocol is intentionally generic
    # and doesn't declare completed_dir (see gm_list_enqueue_service.py).
    gm_list_queue = cast(
        FilesystemGmListQueue,
        get_queue_manager("gm-list", queue_type="gm-list", campaign_name=run.campaign_name),
    )
    completed_results = gm_list_queue.completed_dir / "results"
    resolved = set(identities_with_paths(completed_results).keys())

    if not identities.issubset(resolved):
        return False

    updated = run.model_copy(update={"gm_list_completed_at": datetime.now(UTC)})
    _persist(updated)
    return True


def list_open_job_runs(campaign_name: str) -> List[ScrapeJobRun]:
    """Runs the resilience poller (WorkerService's heartbeat loop) should
    still act on: either stuck waiting for their auto-copy
    (discovery_gen_completed_at set, started_at not - e.g. the process
    that created the run crashed before finishing the copy), or still
    draining (started_at set, gm_list_completed_at not).
    """
    return [
        r
        for r in _load_index(campaign_name)
        if r.discovery_gen_completed_at is not None and r.gm_list_completed_at is None
    ]


def get_job_run(campaign_name: str, run_id: str) -> Optional[ScrapeJobRun]:
    for r in _load_index(campaign_name):
        if r.id == run_id:
            return r
    return None


def get_latest_job_run(campaign_name: str) -> Optional[ScrapeJobRun]:
    """The most recently created run for this campaign, regardless of its
    lifecycle state - None if the campaign has no runs yet."""
    runs = _load_index(campaign_name)
    if not runs:
        return None
    return max(runs, key=lambda r: r.created_at)


def requeue_job_run(campaign_name: str, previous_run_id: str, *, hostname: Optional[str] = None) -> ScrapeJobRun:
    """Creates a fresh ScrapeJobRun that re-scrapes a previous run's exact
    identity set, bypassing gm-list's "already has a completed receipt"
    filter (every identity in a finished run trivially has one, or it
    wouldn't be finished). For the "haven't scraped this campaign in N
    months, there might be new data" use case - Mark, 2026-08-29: re-runs
    the same discovery-gen tiles/phrases without regenerating them.

    Raises ValueError if previous_run_id doesn't exist for this campaign.
    """
    previous = get_job_run(campaign_name, previous_run_id)
    if previous is None:
        raise ValueError(f"No job run '{previous_run_id}' found for campaign '{campaign_name}'")

    identities = load_identities(previous)
    new_run = create_job_run(campaign_name, hostname=hostname)
    new_run = mark_discovery_gen_completed(new_run, identities)
    new_run = enqueue_gm_list_for_run(new_run, rescrape_all=True)
    return new_run
