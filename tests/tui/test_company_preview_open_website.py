from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from cocli.application.services import ServiceContainer
from cocli.models.companies.company import Company
from cocli.models.search import SearchResult
from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_list import CompanyList
from cocli.tui.widgets.company_preview import CompanyPreview
from conftest import wait_for_widget
from textual.widgets import ListView


@pytest.fixture
def preview_company() -> Company:
    return Company(name="Test Co", slug="test-co", domain="test.com")


@pytest.mark.asyncio
async def test_preview_replaces_screenshot_when_highlight_changes(
    preview_company, tmp_path, monkeypatch
):
    screenshot_path = tmp_path / "enrichments" / "screenshot.png"
    screenshot_path.parent.mkdir()
    Image.new("RGB", (4, 4), color=(255, 0, 0)).save(screenshot_path, format="PNG")
    monkeypatch.setattr(Company, "get_local_path", lambda _: tmp_path)

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        preview = CompanyPreview()
        await app.query_one("#app_content").mount(preview)
        await pilot.pause()

        await preview.update_preview(preview_company)
        await preview.update_preview(preview_company)
        await pilot.pause()

        from textual_image.widget import AutoImage

        panel = preview.query_one("#preview-screenshot-panel")
        assert len(list(panel.query(AutoImage))) == 1


@pytest.mark.asyncio
@patch("cocli.tui.widgets.company_preview.open_url", return_value=True)
async def test_preview_open_website_uses_desktop_opener(
    mock_open_url, preview_company
):
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        preview = CompanyPreview()
        await app.query_one("#app_content").mount(preview)
        await pilot.pause()
        await preview.update_preview(preview_company)

        preview.action_open_website()

        mock_open_url.assert_called_once_with("http://test.com")


@pytest.mark.asyncio
@patch("cocli.tui.widgets.company_preview.open_url", return_value=True)
async def test_preview_open_website_skips_opener_without_domain(
    mock_open_url, preview_company
):
    preview_company.domain = None
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        preview = CompanyPreview()
        await app.query_one("#app_content").mount(preview)
        await pilot.pause()
        await preview.update_preview(preview_company)

        preview.action_open_website()

        mock_open_url.assert_not_called()


@pytest.mark.asyncio
@patch("cocli.tui.widgets.company_preview.open_url", return_value=True)
async def test_preview_open_website_skips_when_no_company_loaded(mock_open_url):
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        preview = CompanyPreview()
        await app.query_one("#app_content").mount(preview)
        await pilot.pause()

        preview.action_open_website()

        mock_open_url.assert_not_called()


@pytest.mark.asyncio
@patch("cocli.utils.open_url.open_url", return_value=True)
@patch("cocli.tui.widgets.company_preview.open_url", return_value=True)
@patch("cocli.tui.widgets.company_list.Company.get")
async def test_w_on_company_list_opens_previewed_website(
    mock_get, mock_preview_open_url, mock_utils_open_url, preview_company
):
    mock_get.return_value = preview_company
    mock_search = MagicMock(
        return_value=[
            SearchResult(
                name="Test Co",
                slug="test-co",
                domain="test.com",
                type="company",
                unique_id="test-co",
                tags=[],
                display="",
            )
        ]
    )
    services = ServiceContainer(search_service=mock_search, sync_search=True)
    app = CocliApp(services=services, auto_show=False)

    async with app.run_test() as driver:
        await driver.app.action_show_companies()
        company_list = await wait_for_widget(driver, CompanyList)
        list_view = company_list.query_one("#company_list_view", ListView)
        assert len(list_view.children) == 1
        list_view.focus()
        await driver.pause()

        preview = app.query_one(CompanyPreview)
        if preview.company is None:
            await preview.update_preview(preview_company)

        await driver.press("w")
        await driver.pause()

        assert (
            mock_preview_open_url.called or mock_utils_open_url.called
        ), "open_url was not called from preview or list fallback"
        opener = (
            mock_preview_open_url if mock_preview_open_url.called else mock_utils_open_url
        )
        opener.assert_called_with("http://test.com")
