"""Yank a to-call lead that does not belong on the list.

Exclusion is the durable "don't put this back" bit. The to-call-invalid
queue is the review pile (reason on the record). Removing the pending
to-call file is what takes it off the call list immediately.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


REASON_NONCONFORMING = "to-call-nonconforming"
REASON_HIGH_VALUE = "high-value"
TAG_HIGH_VALUE = "high-value"


def mark_to_call_invalid(
    *,
    campaign: str,
    slug: str,
    domain: Optional[str] = None,
    reason: str = REASON_NONCONFORMING,
) -> Path:
    from cocli.core.exclusions import ExclusionManager
    from cocli.models.campaigns.queues.to_call import ToCallTask
    from cocli.models.campaigns.queues.to_call_invalid import ToCallInvalidTask

    ExclusionManager(campaign).add_exclusion(
        slug=slug, domain=domain, reason=reason
    )

    pending = ToCallTask(
        company_slug=slug,
        domain=domain or "unknown",
        campaign_name=campaign,
        ack_token=None,
    ).get_local_path()
    if pending.exists():
        pending.unlink()

    invalid = ToCallInvalidTask(
        company_slug=slug,
        domain=domain or "unknown",
        campaign_name=campaign,
        reason=reason,
        ack_token=None,
    )
    invalid.save()
    return invalid.get_local_path()


def mark_to_call_high_value(
    *,
    campaign: str,
    slug: str,
    domain: Optional[str] = None,
) -> Path:
    """Tag the company and enqueue the high-value pile. Leaves to-call as-is."""
    from cocli.models.campaigns.queues.to_call_high_value import ToCallHighValueTask
    from cocli.models.companies.company import Company

    company = Company.get(slug)
    if company is not None:
        tags = list(company.tags or [])
        if TAG_HIGH_VALUE not in tags:
            tags.append(TAG_HIGH_VALUE)
            company.tags = tags
            company.save(rebuild_cache=False)

    task = ToCallHighValueTask(
        company_slug=slug,
        domain=domain or "unknown",
        campaign_name=campaign,
        reason=REASON_HIGH_VALUE,
        ack_token=None,
    )
    task.save()
    return task.get_local_path()
