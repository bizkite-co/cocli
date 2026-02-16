import pytest
from cocli.tui.app import CocliApp
from cocli.tui.widgets.application_view import ApplicationView
from cocli.tui.widgets.campaign_selection import CampaignSelection
from cocli.tui.widgets.status_view import StatusView
from conftest import wait_for_widget
from textual.widgets import ListView

@pytest.mark.asyncio
async def test_application_sidebar_stacking():
    """Test that sub-lists are displayed underneath the top-level app menu."""
    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        # Navigate to Application tab
        await driver.press("space")
        await driver.pause(0.1)
        await driver.press("a")
        await driver.pause(0.1)
        
        application_view = await wait_for_widget(driver, ApplicationView)
        nav_list = application_view.query_one("#app_nav_list", ListView)
        
        # 1. Test Operations (Default)
        # Verify ops_list is visible
        ops_list = application_view.query_one("#ops_list", ListView)
        assert ops_list.styles.display != "none"
        
        # 2. Test Campaigns
        nav_list.index = 0
        nav_list.action_select_cursor()
        await driver.pause(0.2)
        
        # Top nav should still be there
        assert nav_list.styles.display != "none"
        
        # Campaign list should now be visible below it
        campaign_list = application_view.query_one(CampaignSelection)
        assert campaign_list.styles.display != "none"
        # Operations list should be hidden
        assert ops_list.styles.display == "none"

        # 3. Test Status
        nav_list.index = 1
        nav_list.action_select_cursor()
        await driver.pause(0.2)
        
        # Campaign list should be hidden
        assert campaign_list.styles.display == "none"
        # Status view should be visible in content area
        status_view = application_view.query_one(StatusView)
        assert status_view.styles.display != "none"
