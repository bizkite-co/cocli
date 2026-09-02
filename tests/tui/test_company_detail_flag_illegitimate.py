"""CompanyDetail's 'x' action flags a company as an illegitimate/
ad-injected Google Maps result via the existing ExclusionManager
(cocli/core/exclusions.py). Moved here from a since-removed
screenshot-viewer modal - the screenshot is now always visible inline,
so the flag action lives directly on the detail screen (Mark, 2026-08-30).
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_detail import CompanyDetail


@pytest.fixture
def mock_company_data(tmp_path: Path):
    enrichment_dir = tmp_path / "companies" / "nemeth-family-interiors" / "enrichments"
    enrichment_dir.mkdir(parents=True)
    return {
        "company": {
            "name": "Nemeth Family Interiors",
            "slug": "nemeth-family-interiors",
            "domain": "nemethfamilyinteriors.com",
        },
        "contacts": [],
        "meetings": [],
        "notes": [],
        "website_data": None,
        "tags": [],
        "enrichment_path": str(enrichment_dir / "website.md"),
    }


@pytest.mark.asyncio
async def test_flag_illegitimate_confirmed_adds_exclusion(mock_company_data):
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()  # on_mount() focuses panel_info

        with patch(
            "cocli.application.to_call_disposition_service.mark_to_call_invalid"
        ) as mock_mark, patch(
            "cocli.core.config.get_campaign", return_value="turboship"
        ):
            await pilot.press("x")
            await pilot.pause()
            await pilot.press("y")
            await pilot.pause()

            mock_mark.assert_called_once_with(
                campaign="turboship",
                slug="nemeth-family-interiors",
                domain="nemethfamilyinteriors.com",
                reason="google-maps-ad-injection",
            )


@pytest.mark.asyncio
async def test_flag_illegitimate_cancelled_does_not_add_exclusion(mock_company_data):
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()  # on_mount() focuses panel_info

        with patch("cocli.core.exclusions.ExclusionManager") as mock_manager_cls:
            await pilot.press("x")
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()

            mock_manager_cls.assert_not_called()


@pytest.mark.asyncio
async def test_action_flag_illegitimate_notifies_when_no_slug(mock_company_data):
    mock_company_data["company"]["slug"] = None
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        with patch.object(app, "notify") as mock_notify:
            detail.action_flag_illegitimate()
            await pilot.pause()

        mock_notify.assert_called_once()
        assert mock_notify.call_args.kwargs.get("severity") == "error"


@pytest.mark.asyncio
async def test_mark_menu_i_marks_invalid(mock_company_data):
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        with patch(
            "cocli.application.to_call_disposition_service.mark_to_call_invalid"
        ) as mock_mark, patch(
            "cocli.core.config.get_campaign", return_value="roadmap"
        ):
            await pilot.press("m")
            await pilot.pause()
            await pilot.press("i")
            await pilot.pause()

            mock_mark.assert_called_once_with(
                campaign="roadmap",
                slug="nemeth-family-interiors",
                domain="nemethfamilyinteriors.com",
                reason="to-call-nonconforming",
            )
