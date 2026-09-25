"""Test that the To-Call filter prioritizes testimonial targets by rank/priority
ahead of regular prospects in DuckDB search.
"""

from __future__ import annotations
from datetime import datetime, UTC
import pytest

from cocli.application.search_service import get_fuzzy_search_results
import cocli.application.search_service as search_service
from cocli.core.paths import paths
from cocli.core.cache import build_cache
from cocli.models.campaigns.queues.to_call import ToCallTask


@pytest.fixture
def to_call_test_env(mock_cocli_env, mocker):
    """Set up a test environment with testimonial targets and cold prospects."""
    campaign = "test/to_call_sorting"
    mocker.patch("cocli.core.config.get_campaign", return_value=campaign)
    mocker.patch("cocli.application.search_service.get_campaign", return_value=campaign)

    # Reset search_service module state
    search_service._con = None
    search_service._last_campaign = None

    companies_dir = paths.companies
    to_call_pending = paths.queue(campaign, "to-call") / "pending"
    to_call_pending.mkdir(parents=True, exist_ok=True)

    # 1. Cold prospect A (no testimonial tag)
    prospect_a_slug = "aaa-cold-prospect"
    comp_a_dir = companies_dir / prospect_a_slug
    comp_a_dir.mkdir(parents=True, exist_ok=True)
    (comp_a_dir / "_index.md").write_text(
        f"---\nname: AAA Cold Prospect\ntags:\n  - {campaign}\n  - prospect\n---\n"
    )
    task_a = ToCallTask(
        company_slug=prospect_a_slug,
        domain="aaacold.com",
        campaign_name=campaign,
        priority=1,
    )
    (to_call_pending / f"{prospect_a_slug}.usv").write_text(task_a.to_usv())

    # 2. Testimonial target B (rank 5)
    target_b_slug = "bbb-testimonial-target"
    comp_b_dir = companies_dir / target_b_slug
    comp_b_dir.mkdir(parents=True, exist_ok=True)
    (comp_b_dir / "_index.md").write_text(
        f"---\nname: BBB Testimonial Target\ntags:\n  - {campaign}\n  - testimonial-target\n  - rta-rank-5\n---\n"
    )
    task_b = ToCallTask(
        company_slug=target_b_slug,
        domain="bbbtestimonial.com",
        campaign_name=campaign,
        priority=5,
        callback_at=datetime.now(UTC),
    )
    (to_call_pending / f"{target_b_slug}.usv").write_text(task_b.to_usv())

    # 3. Testimonial target A (rank 1)
    target_c_slug = "ccc-testimonial-target-top"
    comp_c_dir = companies_dir / target_c_slug
    comp_c_dir.mkdir(parents=True, exist_ok=True)
    (comp_c_dir / "_index.md").write_text(
        f"---\nname: CCC Top Testimonial Target\ntags:\n  - {campaign}\n  - testimonial-target\n  - rta-rank-1\n---\n"
    )
    task_c = ToCallTask(
        company_slug=target_c_slug,
        domain="ccctop.com",
        campaign_name=campaign,
        priority=1,
        callback_at=datetime.now(UTC),
    )
    (to_call_pending / f"{target_c_slug}.usv").write_text(task_c.to_usv())

    # Build cache for test campaign
    build_cache(campaign=campaign)
    return mock_cocli_env


def test_to_call_sorts_testimonial_targets_first_by_priority(to_call_test_env):
    """Testimonial targets must sort before cold prospects, ordered by rank/priority."""
    results = get_fuzzy_search_results(
        "",
        campaign_name="test/to_call_sorting",
        filters={"to_call": True},
        force_rebuild_cache=True,
    )

    assert len(results) == 3
    # First: Rank 1 testimonial target
    assert results[0].slug == "ccc-testimonial-target-top"
    assert results[0].to_call_priority == 1
    assert "testimonial-target" in results[0].tags

    # Second: Rank 5 testimonial target
    assert results[1].slug == "bbb-testimonial-target"
    assert results[1].to_call_priority == 5
    assert "testimonial-target" in results[1].tags

    # Third: Cold prospect (even though its name starts with AAA)
    assert results[2].slug == "aaa-cold-prospect"
    assert "testimonial-target" not in results[2].tags
