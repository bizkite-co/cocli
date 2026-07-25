"""cocli pilot: path helpers bound to station_defs (decision 0010).

Uses stations.paths + declaration-scoped PhaseRef — no free-floating phase
magic strings at the helper boundary when callers pass PhaseRef tokens from
the station's own phases(...) combinator.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from stations.paths import item_dir, relative_phase_shard_key
from stations.segments import PhaseRef, Phases, collect_phases

from cocli.core.paths import paths
from cocli.station_defs.campaigns.indexes.emails import EMAIL_INBOX
from cocli.station_defs.campaigns.queues import QUEUE_PENDING_TEMPLATE


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
    # EMAIL_INBOX declares a single hot phase named "inbox"
    return item_dir(root, EMAIL_INBOX, ph.inbox, email_key, use_shard=True)


def queue_pending_item_path(
    campaign: str,
    queue_name: str,
    task_id: str,
    *,
    phase: Union[str, PhaseRef, None] = None,
) -> Path:
    """``…/queues/{queue}/{phase}/{shard}/{task_id}`` using QUEUE_PENDING_TEMPLATE.

    Default phase is the template's ``pending`` PhaseRef (not a magic string at
    the default-argument site — resolved from the declared combinator).
    """
    ph = collect_phases(QUEUE_PENDING_TEMPLATE.segments)
    if ph is None:
        raise RuntimeError("QUEUE_PENDING_TEMPLATE missing phases(...)")
    phase_ref: Union[str, PhaseRef] = phase if phase is not None else ph.pending
    root = paths.campaign(campaign).queue(queue_name).path
    return item_dir(root, QUEUE_PENDING_TEMPLATE, phase_ref, task_id, use_shard=True)


def queue_pending_relative(task_id: str, *, phase: Union[str, PhaseRef, None] = None) -> str:
    """Relative ``phase/shard/task_id`` for S3 key construction."""
    ph = collect_phases(QUEUE_PENDING_TEMPLATE.segments)
    if ph is None:
        raise RuntimeError("QUEUE_PENDING_TEMPLATE missing phases(...)")
    phase_ref: Union[str, PhaseRef] = phase if phase is not None else ph.pending
    return relative_phase_shard_key(QUEUE_PENDING_TEMPLATE, phase_ref, task_id)
