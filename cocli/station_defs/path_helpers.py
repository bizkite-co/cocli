"""cocli pilot path helpers bound to station_defs (decision 0010).

Uses stations PhaseRef + QueueLayout for DFQ so local and S3 share one relative
path. Prefer QueueLayout for new queue code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from stations.segments import (
    PhaseRef,
    Phases,
    ShardByHash,
    collect_phases,
    collect_shard,
)

from cocli.core.paths import paths
from cocli.core.queue.layout import QueueLayout
from cocli.station_defs.campaigns.indexes.domains import DOMAIN_INBOX
from cocli.station_defs.campaigns.indexes.emails import EMAIL_INBOX
from cocli.station_defs.campaigns.queues import DFQ_QUEUE_STATION


def email_inbox_phases() -> Phases:
    """Phases combinator declared on EMAIL_INBOX (for PhaseRef tokens)."""
    ph = collect_phases(EMAIL_INBOX.segments)
    if ph is None:
        raise RuntimeError("EMAIL_INBOX missing phases(...) segment")
    return ph


def _require_hash_shard(station: object, *, name: str) -> ShardByHash:
    sh = collect_shard(getattr(station, "segments", ()))
    if not isinstance(sh, ShardByHash):
        raise RuntimeError(f"{name} missing shard_by_hash combinator")
    return sh


def email_shard_id(domain: str) -> str:
    """``sha256(domain)[:2]`` from EMAIL_INBOX's declared combinator.

    Production shards by *domain*, not the email address. ``item_dir(..., email)``
    would hash the mailbox and miss existing inbox files.
    """
    return _require_hash_shard(EMAIL_INBOX, name="EMAIL_INBOX").shard_for(domain)


def email_inbox_rel(email_key: str, *, domain: str) -> str:
    """``inbox/{domain-hash}/{email_key}`` relative to the emails index root."""
    ph = email_inbox_phases()
    return f"{ph.inbox.name}/{email_shard_id(domain)}/{email_key}"


def email_shard_file_rel(domain: str) -> str:
    """``shards/{domain-hash}.usv`` relative to the emails index root."""
    return f"shards/{email_shard_id(domain)}.usv"


def email_inbox_item_path(campaign: str, email_key: str, *, domain: str) -> Path:
    """``…/indexes/emails/inbox/{sha256(domain)[:2]}/{email_key}``."""
    root = paths.campaign(campaign).index("emails").path
    return root / email_inbox_rel(email_key, domain=domain)


def domain_shard_id(domain: str) -> str:
    """Same combinator as EMAIL_INBOX (DOMAIN_HASH_SHARD on DOMAIN_INBOX)."""
    return _require_hash_shard(DOMAIN_INBOX, name="DOMAIN_INBOX").shard_for(domain)


def domain_inbox_leaf(domain: str, *, filename: str) -> str:
    """``{domain-hash}/{filename}`` under DomainIndexManager.inbox_root."""
    return f"{domain_shard_id(domain)}/{filename}"


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
