from pathlib import Path
from unittest.mock import patch

import pytest

from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_detail import CompanyDetail
from cocli.tui.widgets.screenshot_viewer_modal import ScreenshotViewerModal


@pytest.fixture
def mock_company_data(tmp_path: Path):
    enrichment_dir = tmp_path / "companies" / "test-co" / "enrichments"
    enrichment_dir.mkdir(parents=True)
    return {
        "company": {
            "name": "Test Co",
            "slug": "test-co",
            "domain": "test.com",
        },
        "contacts": [],
        "meetings": [],
        "notes": [],
        "website_data": None,
        "tags": [],
        "enrichment_path": str(enrichment_dir / "website.md"),
    }


@pytest.mark.asyncio
async def test_action_view_screenshot_pushes_modal_with_computed_path(mock_company_data):
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        detail.action_view_screenshot()
        await pilot.pause()

        modal = app.screen_stack[-1]
        assert isinstance(modal, ScreenshotViewerModal)
        assert modal.company_slug == "test-co"
        assert modal.domain == "test.com"
        expected = Path(mock_company_data["enrichment_path"]).parent / "screenshot.png"
        assert modal.screenshot_path == expected


@pytest.mark.asyncio
async def test_action_view_screenshot_notifies_when_no_slug(mock_company_data):
    mock_company_data["company"]["slug"] = None
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        with patch.object(app, "notify") as mock_notify:
            detail.action_view_screenshot()
            await pilot.pause()

        mock_notify.assert_called_once()
        assert mock_notify.call_args.kwargs.get("severity") == "error"
        assert not isinstance(app.screen_stack[-1], ScreenshotViewerModal)
