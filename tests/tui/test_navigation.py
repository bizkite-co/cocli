import pytest
from cocli.tui.app import CocliApp
from cocli.tui.widgets.main_menu import MainMenu
from cocli.tui.screens.company_list import CompanyList
from cocli.tui.screens.company_detail import CompanyDetailScreen
from textual.widgets import ListView
from unittest.mock import patch


mock_detail_data = {
    "company": {"name": "Selected Company", "slug": "selected-company", "domain": "selected.com"},
    "tags": [], "content": "", "website_data": None, "contacts": [], "meetings": [], "notes": []
}

@pytest.mark.asyncio
async def test_h_key_goes_back():
    """
    Tests that pressing 'h' on a sub-screen returns to the main menu.
    """
    app = CocliApp()
    async with app.run_test() as driver:
        # Select 'Companies' from the main menu
        await driver.press("j") # Move to Companies
        await driver.press("l") # Select Companies
        await driver.pause()
        
        # Check that we are on the company list screen
        assert isinstance(app.query_one("#body").children[0], CompanyList)
        
        # Move focus from the search input to the list view
        app.query_one(CompanyList).query_one(ListView).focus()
        await driver.pause()
        
        # Press 'h' to go back
        await driver.press("h")
        await driver.pause()

        # Check that we are back on the main menu
        assert isinstance(app.query_one("#main_menu"), MainMenu)


@pytest.mark.asyncio
@patch('cocli.tui.app.get_company_details_for_view')
async def test_l_key_selects_item(mock_get_company_details):
    mock_get_company_details.return_value = mock_detail_data
    """
    Tests that pressing 'l' on a ListView item triggers the selection of that item.
    """
    app = CocliApp()
    async with app.run_test() as driver:
        # Select 'Companies' from the main menu
        await driver.press("j") # Move to Companies
        await driver.press("l") # Select Companies
        await driver.pause()
        
        # Check that we are on the company list screen
        assert isinstance(app.query_one("#body").children[0], CompanyList)
        
        # Move focus from the search input to the list view
        app.query_one(CompanyList).query_one(ListView).focus()
        await driver.pause()

        # Press 'l' to select the item
        await driver.press("l")
        await driver.pause()

        # Check that the company detail screen is displayed
        assert isinstance(app.query_one("#body").children[0], CompanyDetailScreen)
