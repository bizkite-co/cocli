from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from cocli.application.to_call_disposition_service import (
    REASON_NONCONFORMING,
    mark_to_call_invalid,
)
from cocli.core.exclusions import ExclusionManager
from cocli.core.paths import paths
from cocli.models.campaigns.queues.to_call import ToCallTask
from cocli.models.campaigns.queues.to_call_invalid import ToCallInvalidTask


def test_mark_to_call_invalid_excludes_removes_pending_and_enqueues_review(
    tmp_path: Path,
) -> None:
    with patch.object(paths, "root", tmp_path):
        campaign = "roadmap"
        slug = "aamco-transmission-total-car-care"
        domain = "aamco.com"

        pending = ToCallTask(
            company_slug=slug,
            domain=domain,
            campaign_name=campaign,
            ack_token=None,
        )
        pending.save()
        assert pending.get_local_path().exists()

        dest = mark_to_call_invalid(
            campaign=campaign, slug=slug, domain=domain
        )

        assert dest.exists()
        assert dest == ToCallInvalidTask(
            company_slug=slug,
            domain=domain,
            campaign_name=campaign,
            ack_token=None,
        ).get_local_path()
        assert not pending.get_local_path().exists()
        assert ExclusionManager(campaign).is_excluded(slug=slug, domain=domain)

        loaded = ToCallInvalidTask.from_usv(dest.read_text())
        assert loaded.reason == REASON_NONCONFORMING
        assert loaded.company_slug == slug


def test_mark_to_call_high_value_keeps_pending_and_writes_queue(
    tmp_path: Path,
) -> None:
    from cocli.application.to_call_disposition_service import mark_to_call_high_value
    from cocli.models.campaigns.queues.to_call_high_value import ToCallHighValueTask

    with patch.object(paths, "root", tmp_path):
        campaign = "roadmap"
        slug = "hot-lead-co"
        domain = "hotlead.com"

        pending = ToCallTask(
            company_slug=slug,
            domain=domain,
            campaign_name=campaign,
            ack_token=None,
        )
        pending.save()

        dest = mark_to_call_high_value(
            campaign=campaign, slug=slug, domain=domain
        )

        assert dest.exists()
        assert pending.get_local_path().exists()
        assert not ExclusionManager(campaign).is_excluded(slug=slug, domain=domain)
        loaded = ToCallHighValueTask.from_usv(dest.read_text())
        assert loaded.reason == "high-value"
        assert loaded.company_slug == slug
