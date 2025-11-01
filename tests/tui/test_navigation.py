import pytest
from cocli.tui.app import CocliApp
from cocli.tui.screens.main_menu import MainMenu
from cocli.tui.screens.company_list import CompanyList
from cocli.tui.screens.company_detail import CompanyDetailScreen


@pytest.mark.asyncio
async def test_h_key_goes_back():
    """
    Tests that pressing 'h' on a sub-screen returns to the main menu.
    """
    app = CocliApp()
    async with app.run_test() as driver:
        # Push the company list screen
        await driver.app.push_screen(CompanyList())
        await driver.pause()

        # Check that we are on the company list screen
        assert isinstance(app.screen, CompanyList)

        # Move focus from the search input to the list view
        await driver.press("tab")
        await driver.pause()

        # Press 'h' to go back
        await driver.press("h")
        await driver.pause()

        # Check that we are back on the main menu
        assert isinstance(app.screen, MainMenu)


@pytest.mark.asyncio
async def test_l_key_selects_item():
    """
    Tests that pressing 'l' on a ListView item triggers the selection of that item.
    """
    app = CocliApp()
    async with app.run_test() as driver:
        # Push the company list screen
        await driver.app.push_screen(CompanyList())
        await driver.pause()

        # Check that we are on the company list screen
        assert isinstance(app.screen, CompanyList)

        # Move focus from the search input to the list view
        await driver.press("tab")
        await driver.pause()

        # Press 'l' to select the item
        await driver.press("l")
        await driver.pause()

        # Check that the company detail screen is displayed
        assert isinstance(app.screen, CompanyDetailScreen)