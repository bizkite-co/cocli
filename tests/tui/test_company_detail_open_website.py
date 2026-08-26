from unittest.mock import patch

import pytest

from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_detail import CompanyDetail


@pytest.fixture
def mock_company_data():
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
    }


@pytest.mark.asyncio
@patch("cocli.tui.widgets.company_detail.open_url", return_value=True)
async def test_action_open_website_uses_desktop_opener(
    mock_open_url, mock_company_data
):
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        detail.action_open_website()

        mock_open_url.assert_called_once_with("http://test.com")


@pytest.mark.asyncio
@patch("cocli.tui.widgets.company_detail.open_url", return_value=True)
async def test_action_open_website_skips_opener_without_domain(
    mock_open_url, mock_company_data
):
    mock_company_data["company"]["domain"] = None
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        detail.action_open_website()

        mock_open_url.assert_not_called()


@pytest.mark.asyncio
@patch("cocli.tui.widgets.company_detail.open_url", return_value=False)
async def test_action_open_website_does_not_pretend_success_when_launch_fails(
    mock_open_url, mock_company_data
):
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        detail.action_open_website()

        mock_open_url.assert_called_once_with("http://test.com")
