"""cocli pilot path helpers bound to station_defs (decision 0010).

Uses stations PhaseRef + QueueLayout for DFQ so local and S3 share one relative
path. Prefer QueueLayout for new queue code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from stations.paths import item_dir
from stations.segments import PhaseRef, Phases, collect_phases

from cocli.core.paths import paths
from cocli.core.queue.layout import QueueLayout
from cocli.station_defs.campaigns.indexes.emails import EMAIL_INBOX
from cocli.station_defs.campaigns.queues import DFQ_QUEUE_STATION


def email_inbox_phases() -> Phases:
    """Phases combinator declared on EMAIL_INBOX (for PhaseRef tokens)."""
    ph = collect_phases(EMAIL_INBOX.segments)
    if ph is None:
        raise RuntimeError("EMAIL_INBOX missing phases(...) segment")
    return ph


def email_inbox_item_path(campaign: str, email_key: str) -> Path:
    """``…/indexes/emails/inbox/{shard}/{email_key}`` via station combinators."""
    root = paths.campaign(campaign).index("emails").path
    ph = email_inbox_phases()
    return item_dir(root, EMAIL_INBOX, ph.inbox, email_key, use_shard=True)


def dfq_layout(campaign: str, queue_name: str) -> QueueLayout:
    """QueueLayout for standard DFQ (place_id 6th-char shard)."""
    local_root = paths.campaign(campaign).queue(queue_name).path
    return QueueLayout(
        station=DFQ_QUEUE_STATION,
        campaign_name=campaign,
        queue_name=queue_name,
        local_root=local_root,
    )


def queue_pending_item_path(
    campaign: str,
    queue_name: str,
    task_id: str,
    *,
    phase: Union[str, PhaseRef, None] = None,
) -> Path:
    """``…/queues/{queue}/{phase}/{shard}/{task_id}`` via QueueLayout."""
    layout = dfq_layout(campaign, queue_name)
    phase_ref: Union[str, PhaseRef] = (
        phase if phase is not None else layout.phases.pending
    )
    return layout.item_dir(phase_ref, task_id)


def queue_pending_relative(
    task_id: str,
    *,
    phase: Union[str, PhaseRef, None] = None,
    station: object = None,
) -> str:
    """Relative ``phase/shard/task_id`` (shared by local and S3)."""
    from cocli.core.queue.layout import task_rel_under_phase

    st = station if station is not None else DFQ_QUEUE_STATION
    ph = collect_phases(getattr(st, "segments", ()))
    if ph is None:
        raise RuntimeError("station missing phases(...)")
    phase_ref: Union[str, PhaseRef] = phase if phase is not None else ph.pending
    return task_rel_under_phase(st, phase_ref, task_id)  # type: ignore[arg-type]
