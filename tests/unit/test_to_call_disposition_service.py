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
