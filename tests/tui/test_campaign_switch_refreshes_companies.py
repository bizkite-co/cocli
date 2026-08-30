"""Switching campaigns navigates back to the Companies screen's "All Leads"
template but action_show_companies() reuses the existing CompanySearchView
to preserve search state across normal screen switches - so without an
explicit re-query, the company list just keeps showing whatever rows were
last fetched for the OLD campaign (Mark, 2026-08-30).
"""

from unittest.mock import MagicMock

import pytest

from cocli.application.services import ServiceContainer
from cocli.models.search import SearchResult
from cocli.tui.app import CocliApp
from cocli.tui.widgets.application_view import ApplicationView
from cocli.tui.widgets.company_search import CompanySearchView


def _result(slug: str) -> SearchResult:
    return SearchResult(
        name=slug,
        slug=slug,
        type="company",
        unique_id=slug,
        tags=[],
        display=slug,
    )


@pytest.mark.asyncio
async def test_campaign_activation_re_queries_the_new_campaign() -> None:
    old_results = [_result("old-campaign-co")]
    new_results = [_result("new-campaign-co")]
    mock_search = MagicMock(side_effect=[old_results, new_results])

    services = ServiceContainer(
        search_service=mock_search,
        template_counts_service=MagicMock(return_value={}),
        sync_search=True,
    )
    app = CocliApp(services=services, auto_show=False)

    async with app.run_test() as pilot:
        await app.action_show_companies()
        await pilot.pause()

        search_view = app.query_one(CompanySearchView)
        assert [r.slug for r in search_view.company_list.filtered_fz_items] == [
            "old-campaign-co"
        ]

        await app.on_application_view_campaign_activated(
            ApplicationView.CampaignActivated("other-campaign")
        )
        await pilot.pause()

        assert services.campaign_name == "other-campaign"
        assert mock_search.call_count == 2
        assert [r.slug for r in search_view.company_list.filtered_fz_items] == [
            "new-campaign-co"
        ]
