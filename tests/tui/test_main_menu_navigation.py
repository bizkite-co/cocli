import pytest
from cocli.tui.app import CocliApp
from cocli.tui.widgets.main_menu import MainMenu



@pytest.mark.asyncio
async def test_k_key_moves_up_in_main_menu():
    """
    Tests that pressing 'k' on the main menu moves the cursor up.
    """
    app = CocliApp()
    async with app.run_test() as driver:
        # Check that we are on the main menu screen
        assert isinstance(app.query_one("#main_menu"), MainMenu)

        # Press 'j' to move down
        await driver.press("j")
        await driver.pause()

        # Press 'k' to move up
        await driver.press("k")
        await driver.pause()

        # Check that the first item is highlighted
        assert app.query_one("#main_menu").query_one("ListView").index == 0
