"""Copies discovery-gen's completed, per-phrase-tile output into gm-list's
own pending/ - the missing half of the pipeline (see task-agent ticket
gm-list-queue-regressed-from-pendingcompleted-pattern-diverged-from-its-own-stations-declaration,
"Goal-state decision v2").

discovery-gen/completed/ and gm-list/pending/ both hold ScrapeTask-shaped
files at the same relative path (shard/lat/lon/phrase.usv - both derive
their shard from the same get_geo_shard(lat) function), so this is a real,
transformation-free file copy, not a model coercion.

Dedup is orchestration's job, done here at copy time, not the queue's -
see the "orchestration-vs-queue-mechanics" principle in the ticket. Default
behavior skips anything with an existing gm-list completed receipt
(reconcile_identities(...).left_only); --rescrape-all bypasses that.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, cast

from ..core.paths import paths
from ..core.queue.factory import get_queue_manager
from ..core.queue.filesystem import FilesystemGmListQueue
from ..core.queue.reconcile import identities_with_paths, reconcile_identities
from ..models.campaigns.queues.gm_list import ScrapeTask


@dataclass(frozen=True)
class EnqueueResult:
    candidates: int
    copied: int
    skipped_already_scraped: int
    dry_run: bool


def _discovery_gen_completed_dir(campaign_name: str) -> Path:
    return (
        paths.campaign(campaign_name)
        .queue(ScrapeTask.SOURCE_QUEUE)
        .state(ScrapeTask.SOURCE_STATE)
    )


def enqueue_unscraped_to_gm_list_pending(
    campaign_name: str,
    limit: Optional[int] = None,
    rescrape_all: bool = False,
    dry_run: bool = False,
) -> EnqueueResult:
    """Copy discovery-gen/completed/ items into gm-list/pending/.

    Default: only items with no existing gm-list completed receipt.
    rescrape_all: copy everything, ignoring receipts.
    limit: copy at most this many items (deterministic order - sorted by
    identity), for the "enqueue a few items at a time" use case.
    """
    discovery_gen_completed = _discovery_gen_completed_dir(campaign_name)
    # queue_type="gm-list" always resolves to FilesystemGmListQueue for the
    # filesystem provider; CampaignQueueProtocol is intentionally generic and
    # doesn't declare pending_dir/completed_dir.
    gm_list_queue = cast(
        FilesystemGmListQueue,
        get_queue_manager("gm-list", queue_type="gm-list", campaign_name=campaign_name),
    )
    gm_list_completed_results = gm_list_queue.completed_dir / "results"
    gm_list_pending = gm_list_queue.pending_dir

    source_map = identities_with_paths(discovery_gen_completed)

    if rescrape_all:
        to_copy_ids = set(source_map.keys())
        skipped_already_scraped = 0
    else:
        result = reconcile_identities(discovery_gen_completed, gm_list_completed_results)
        to_copy_ids = set(result.left_only)
        skipped_already_scraped = len(result.intersection)

    candidates = len(to_copy_ids)
    ordered_ids = sorted(to_copy_ids)
    if limit is not None:
        ordered_ids = ordered_ids[:limit]

    copied = 0
    for identity in ordered_ids:
        source_path = source_map[identity]
        dest_path = gm_list_pending / source_path.relative_to(discovery_gen_completed)
        if not dry_run:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, dest_path)
        copied += 1

    return EnqueueResult(
        candidates=candidates,
        copied=copied,
        skipped_already_scraped=skipped_already_scraped,
        dry_run=dry_run,
    )
