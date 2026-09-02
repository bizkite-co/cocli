"""Yank a to-call lead that does not belong on the list.

Exclusion is the durable "don't put this back" bit. The to-call-invalid
queue is the review pile (reason on the record). Removing the pending
to-call file is what takes it off the call list immediately.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


REASON_NONCONFORMING = "to-call-nonconforming"
REASON_AD_INJECTION = "google-maps-ad-injection"


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
