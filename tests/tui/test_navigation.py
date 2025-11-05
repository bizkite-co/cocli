import pytest
from cocli.tui.app import CocliApp

from cocli.tui.widgets.company_list import CompanyList
from cocli.tui.widgets.company_detail import CompanyDetail
from textual.widgets import ListView
from unittest.mock import patch
from conftest import wait_for_widget
from cocli.models.search import SearchResult

mock_detail_data = {
    "company": {"name": "Selected Company", "slug": "selected-company", "domain": "selected.com"},
    "tags": [], "content": "", "website_data": None, "contacts": [], "meetings": [], "notes": []
}

@pytest.mark.asyncio
@patch('cocli.tui.app.get_company_details_for_view')
@patch('cocli.tui.widgets.company_list.get_filtered_items_from_fz')
async def test_l_key_selects_item(mock_get_fz_items, mock_get_company_details):
    """
    Tests that pressing 'l' on a ListView item triggers the selection of that item.
    """
    mock_get_fz_items.return_value = [
        SearchResult(name="Test Company", slug="test-company", domain="test.com", type="company", unique_id="test-company", tags=[], display=""),
    ]
    mock_get_company_details.return_value = mock_detail_data

    app = CocliApp()
    async with app.run_test() as driver:
        await driver.press("space", "c")
        company_list_screen = await wait_for_widget(driver, CompanyList)
        assert isinstance(company_list_screen, CompanyList)

        company_list_screen.query_one(ListView).focus()

        await driver.press("l")

        company_detail = await wait_for_widget(driver, CompanyDetail)
        assert isinstance(company_detail, CompanyDetail)
        mock_get_company_details.assert_called_once_with("test-company")

@pytest.mark.asyncio
@patch('cocli.tui.app.get_company_details_for_view')
@patch('cocli.tui.widgets.company_list.get_filtered_items_from_fz')
async def test_enter_key_selects_item_in_company_list(mock_get_fz_items, mock_get_company_details):
    """
    Tests that pressing 'enter' on a ListView item triggers the selection of that item.
    """
    mock_get_fz_items.return_value = [
        SearchResult(name="Test Company", slug="test-company", domain="test.com", type="company", unique_id="test-company", tags=[], display=""),
    ]
    mock_get_company_details.return_value = mock_detail_data

    app = CocliApp()
    async with app.run_test() as driver:
        await driver.press("space", "c")
        company_list_screen = await wait_for_widget(driver, CompanyList)
        assert isinstance(company_list_screen, CompanyList)

        # Simulate typing in the search input
        await driver.press("T", "e", "s", "t")

        # Press 'enter' to select the item
        await driver.press("enter")

        company_detail = await wait_for_widget(driver, CompanyDetail)
        assert isinstance(company_detail, CompanyDetail)
        mock_get_company_details.assert_called_once_with("test-company")