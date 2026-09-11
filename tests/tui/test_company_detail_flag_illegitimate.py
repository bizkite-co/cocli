"""CompanyDetail mark prefix: ``m`` then ``i`` / ``h``, and ``x`` = invalid."""

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
async def test_x_marks_invalid_immediately(mock_company_data):
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        with patch(
            "cocli.application.to_call_disposition_service.mark_to_call_invalid"
        ) as mock_mark, patch(
            "cocli.core.config.get_campaign", return_value="turboship"
        ):
            await pilot.press("x")
            await pilot.pause()

            mock_mark.assert_called_once_with(
                campaign="turboship",
                slug="nemeth-family-interiors",
                domain="nemethfamilyinteriors.com",
                reason="to-call-nonconforming",
            )


@pytest.mark.asyncio
async def test_action_mark_invalid_notifies_when_no_slug(mock_company_data):
    mock_company_data["company"]["slug"] = None
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        with patch.object(app, "notify") as mock_notify:
            detail.action_mark_invalid()
            await pilot.pause()

        mock_notify.assert_called_once()
        assert mock_notify.call_args.kwargs.get("severity") == "error"


@pytest.mark.asyncio
async def test_mark_prefix_i_marks_invalid(mock_company_data):
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
            bar = detail.query_one("#mark-prefix-bar")
            assert "hidden" not in bar.classes
            await pilot.press("i")
            await pilot.pause()

            mock_mark.assert_called_once_with(
                campaign="roadmap",
                slug="nemeth-family-interiors",
                domain="nemethfamilyinteriors.com",
                reason="to-call-nonconforming",
            )
            assert "hidden" in bar.classes


@pytest.mark.asyncio
async def test_mark_prefix_alt_s_cancels(mock_company_data):
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        with patch(
            "cocli.application.to_call_disposition_service.mark_to_call_invalid"
        ) as mock_mark:
            await pilot.press("m")
            await pilot.pause()
            await pilot.press("alt+s")
            await pilot.pause()
            mock_mark.assert_not_called()
            assert "hidden" in detail.query_one("#mark-prefix-bar").classes


@pytest.mark.asyncio
async def test_mark_prefix_h_marks_high_value(mock_company_data):
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        with patch(
            "cocli.application.to_call_disposition_service.toggle_to_call_high_value",
            return_value=True,
        ) as mock_toggle, patch(
            "cocli.core.config.get_campaign", return_value="roadmap"
        ):
            await pilot.press("m")
            await pilot.pause()
            await pilot.press("h")
            await pilot.pause()

            mock_toggle.assert_called_once_with(
                campaign="roadmap",
                slug="nemeth-family-interiors",
                domain="nemethfamilyinteriors.com",
            )


@pytest.mark.asyncio
async def test_mark_prefix_v_marks_valid(mock_company_data):
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        with patch(
            "cocli.application.to_call_disposition_service.mark_to_call_valid"
        ) as mock_mark, patch(
            "cocli.core.config.get_campaign", return_value="roadmap"
        ):
            await pilot.press("m")
            await pilot.pause()
            bar = detail.query_one("#mark-prefix-bar")
            assert "hidden" not in bar.classes
            await pilot.press("v")
            await pilot.pause()

            mock_mark.assert_called_once_with(
                campaign="roadmap",
                slug="nemeth-family-interiors",
                domain="nemethfamilyinteriors.com",
            )
            assert "hidden" in bar.classes
