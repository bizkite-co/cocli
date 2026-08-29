from datetime import UTC, datetime
from typing import ClassVar, List, Optional

from pydantic import Field

from ..base import BaseUsvModel


class ScrapeJobRun(BaseUsvModel):
    """One discovery-gen generation run's lineage through gm-list scraping.

    Created at the start of `process_tile_queue()` (map-tile/pending ->
    discovery-gen/completed - see cocli/services/tile_queue_processor.py),
    the only thing that can ever cause new work to land in
    gm-list/pending/. gm-list/pending/ draining to zero is NOT itself a
    trigger for re-enqueuing - see cocli/application/worker_service.py
    commit a27b1b81 for why a blind pending==0 trigger is wrong (it can't
    tell "discovery-gen has more real work" apart from "this campaign's
    current batch is genuinely fully scraped").

    Stored twice: one line per run in the campaign-wide
    campaigns/{campaign}/job-runs/job-runs.usv index (fast listing, this
    model's own to_usv()/from_usv()), and the same fields as
    campaigns/{campaign}/job-runs/{id}/metadata.json (JSON, via
    model_dump_json() - same model, no separate schema to keep in sync).
    The run's own identity snapshot (which discovery-gen identities this
    run is responsible for - see cocli/core/queue/reconcile.py for the
    identity format) lives alongside as a plain newline-separated list at
    campaigns/{campaign}/job-runs/{id}/identities.usv - not part of this
    model, since it can be arbitrarily large and isn't itself index data.

    Field order is load-bearing for the USV index (BaseUsvModel derives
    column position from declaration order) - append new fields at the
    end, never insert.
    """

    SCHEMA_UPDATED_AT: ClassVar[str] = "2026-08-29T00:00:00+00:00"

    id: str
    campaign_name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Set once process_tile_queue() finishes writing this run's
    # discovery-gen/completed/ output (identities.usv captures exactly
    # what it wrote, not a before/after directory diff - see module
    # docstring and the ticket this implements for why that distinction
    # matters when two runs' generation windows overlap in time).
    discovery_gen_completed_at: Optional[datetime] = None

    # Set once this run's identity set has been copied into
    # gm-list/pending/ (cocli/application/gm_list_enqueue_service.py,
    # scoped to identity_scope=this run's snapshot). The only path that
    # can ever set this is an explicit run - see module docstring.
    started_at: Optional[datetime] = None

    # Set once every identity in this run's snapshot has reached
    # completed-or-failed in gm-list (not 100% success - real scraping
    # always has some navigation_failed rate).
    gm_list_completed_at: Optional[datetime] = None

    # Total identities in this run's snapshot, captured at
    # discovery_gen_completed_at - lets a reader compute "N of M done"
    # progress without re-reading identities.usv.
    identity_count: int = 0

    # gm_details/enrichment lineage tracking is explicitly deferred (see
    # the ticket this implements) - this just records intent for now.
    queues_involved: List[str] = Field(
        default_factory=lambda: ["gm-list", "gm-details", "enrichment"]
    )
