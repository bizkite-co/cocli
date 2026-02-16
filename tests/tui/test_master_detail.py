import pytest
from cocli.tui.app import CocliApp
from cocli.tui.widgets.campaign_selection import CampaignSelection
from cocli.tui.widgets.application_view import ApplicationView
from conftest import wait_for_widget
from textual.widgets import ListView

@pytest.mark.asyncio
async def test_application_hub_layout(tmp_path, monkeypatch):
    """Test that the application hub has the correct three-pane stacked layout."""
    # Arrange
    monkeypatch.setenv("COCLI_CONFIG_HOME", str(tmp_path))
    (tmp_path / "cocli_config.toml").write_text("[tui]\nmaster_width = 40\n")

    app = CocliApp(auto_show=False)

    async with app.run_test() as driver:
        # Wait for initial on_mount
        await driver.pause(0.5)
        
        # Act
        await driver.press("space")
        await driver.pause(0.1)
        await driver.press("a")
        await driver.pause(0.1)
        
        # Identify ApplicationView
        application_view = await wait_for_widget(driver, ApplicationView)
        
        # Verify three-pane structure
        assert len(application_view.query("#app_sidebar_column")) == 1
        assert len(application_view.query("#app_main_content")) == 1
        assert len(application_view.query("#app_recent_runs")) == 1
        
        # Navigate to Campaigns category (index 0 in app_nav_list)
        nav_list = application_view.query_one("#app_nav_list", ListView)
        nav_list.focus()
        nav_list.index = 0
        nav_list.action_select_cursor()
        
        await driver.pause(0.5)
        
        # Verify CampaignSelection is visible
        campaign_list = application_view.query_one(CampaignSelection)
        assert campaign_list.visible
