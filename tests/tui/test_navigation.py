import pytest
from unittest.mock import patch

from cocli.tui.app import CocliApp
from cocli.tui.screens.company_list import CompanyList
from cocli.tui.screens.main_menu import MainMenu


@pytest.mark.asyncio
async def test_h_key_goes_back():
    """Test that pressing 'h' goes back to the previous screen."""
    app = CocliApp()
    async with app.run_test() as driver:
        await driver.app.push_screen(CompanyList())
        await driver.pause()
        assert isinstance(app.screen, CompanyList)

        await driver.press("h")
        await driver.pause()

        assert isinstance(app.screen, MainMenu)


@pytest.mark.asyncio
@patch("cocli.tui.screens.company_list.CompanyList.on_key")
async def test_l_key_selects_item(mock_on_key):
    """Test that pressing 'l' selects an item in a list."""
    app = CocliApp()
    async with app.run_test() as driver:
        await driver.app.push_screen(CompanyList())
        await driver.pause()

        await driver.press("l")
        await driver.pause()

        mock_on_key.assert_called_once()