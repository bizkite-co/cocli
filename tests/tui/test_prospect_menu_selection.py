import pytest
from unittest.mock import MagicMock
from cocli.tui.app import CocliApp
from cocli.tui.widgets.prospect_menu import ProspectMenu
from textual.widgets import ListView
from conftest import wait_for_screen

@pytest.mark.asyncio
async def test_prospect_menu_selection_not_crashing():
    """Test that selecting an item in the ProspectMenu does not crash the app."""
    app = CocliApp(auto_show=False)
    
    # Mock services to avoid actual network/file side effects during this TUI test
    app.services.reporting_service.get_campaign_stats = MagicMock(return_value={})
    
    async with app.run_test() as driver:
        await driver.pause(0.5)
        # Navigate to Prospect Menu
        await driver.press("space")
        await driver.pause(0.1)
        await driver.press("s")
        
        prospect_screen = await wait_for_screen(driver, ProspectMenu)
        list_view = prospect_screen.query_one(ListView)
        
        # Select "View Campaign Report" (index 1)
        list_view.index = 1
        await driver.press("enter")
        await driver.pause(0.2)
        
        # Check that we didn't crash and the screen is still there
        assert app.screen.__class__ == ProspectMenu
        # Verify the notification was sent (textual-specific check if possible, or just assume no crash is success)
