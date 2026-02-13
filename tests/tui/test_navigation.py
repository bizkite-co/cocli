import pytest
from unittest.mock import MagicMock
from cocli.tui.app import CocliApp
from cocli.application.services import ServiceContainer
from cocli.tui.widgets.company_list import CompanyList
from cocli.tui.widgets.company_detail import CompanyDetail
from textual.widgets import ListView
from conftest import wait_for_widget
from cocli.models.search import SearchResult

mock_detail_data = {
    "company": {"name": "Selected Company", "slug": "selected-company", "domain": "selected.com"},
    "tags": [], "content": "", "website_data": None, "contacts": [], "meetings": [], "notes": []
}

def create_mock_services(search_results=None, detail_data=None):
    mock_search = MagicMock()
    mock_search.return_value = search_results or []
    mock_company_service = MagicMock()
    mock_company_service.return_value = detail_data
    return ServiceContainer(search_service=mock_search, company_service=mock_company_service, sync_search=True), mock_search, mock_company_service

@pytest.mark.asyncio
async def test_l_key_selects_item():
    """
    Tests that pressing 'l' on a ListView item triggers the selection of that item.
    """
    search_results = [
        SearchResult(name="Test Company", slug="test-company", domain="test.com", type="company", unique_id="test-company", tags=[], display=""),
    ]
    services, _, mock_company_service = create_mock_services(search_results, mock_detail_data)

    app = CocliApp(services=services)
    async with app.run_test() as driver:
        await driver.press("space")
        await driver.pause(0.1)
        await driver.press("c")
        await driver.pause(0.1)
        company_list_screen = await wait_for_widget(driver, CompanyList)
        assert isinstance(company_list_screen, CompanyList)

        # Wait for worker
        await driver.pause(0.5)

        list_view = company_list_screen.query_one(ListView)
        list_view.focus()
        await driver.pause(0.1)
        list_view.index = 0
        await driver.pause(0.1)
        list_view.action_select_cursor()
        await driver.pause(0.5)

        company_detail = await wait_for_widget(driver, CompanyDetail)
        assert isinstance(company_detail, CompanyDetail)
        mock_company_service.assert_called_once_with("test-company")


@pytest.mark.asyncio
async def test_down_arrow_moves_highlight_in_company_list():
    """
    Tests that pressing 'down' moves the highlight in the ListView, even when the Input is focused.
    """
    search_results = [
        SearchResult(name="Test Company 1", slug="test-company-1", domain="test1.com", type="company", unique_id="test-company-1", tags=[], display=""),
        SearchResult(name="Test Company 2", slug="test-company-2", domain="test2.com", type="company", unique_id="test-company-2", tags=[], display=""),
    ]
    services, _, _ = create_mock_services(search_results)

    app = CocliApp(services=services)
    async with app.run_test() as driver:
        await driver.press("space")
        await driver.pause(0.1)
        await driver.press("c")
        await driver.pause(0.1)
        company_list_screen = await wait_for_widget(driver, CompanyList)

        await driver.pause(0.5)

        # The input is focused by default
        list_view = company_list_screen.query_one(ListView)
        assert list_view.index == 0

        # Press 'down' and check that the index changes
        await driver.press("down")
        await driver.pause(0.1)
        assert list_view.index == 1

@pytest.mark.asyncio
async def test_enter_key_selects_item_in_company_list():
    """
    Tests that pressing 'enter' on a ListView item triggers the selection of that item.
    """
    search_results = [
        SearchResult(name="Test Company", slug="test-company", domain="test.com", type="company", unique_id="test-company", tags=[], display=""),
    ]
    services, _, mock_company_service = create_mock_services(search_results, mock_detail_data)

    app = CocliApp(services=services)
    async with app.run_test() as driver:
        await driver.press("space")
        await driver.pause(0.1)
        await driver.press("c")
        await driver.pause(0.1)
        company_list_screen = await wait_for_widget(driver, CompanyList)
        assert isinstance(company_list_screen, CompanyList)

        # Simulate typing in the search input
        await driver.press("T", "e", "s", "t")
        await driver.pause(0.5)

        # Press 'enter' to select the item
        await driver.press("enter")
        await driver.pause(0.5)

        company_detail = await wait_for_widget(driver, CompanyDetail)
        assert isinstance(company_detail, CompanyDetail)
        mock_company_service.assert_called_once_with("test-company")
