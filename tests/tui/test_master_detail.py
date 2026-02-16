import pytest
from cocli.tui.app import CocliApp
from cocli.tui.widgets.master_detail import MasterDetailView
from cocli.tui.widgets.campaign_selection import CampaignSelection
from cocli.tui.widgets.application_view import ApplicationView
from conftest import wait_for_widget
from textual.widgets import ListView

@pytest.mark.asyncio
async def test_master_detail_layout(tmp_path, monkeypatch):
    """Test that the master-detail view is laid out horizontally."""
    # Arrange
    monkeypatch.setenv("COCLI_CONFIG_HOME", str(tmp_path))
    (tmp_path / "cocli_config.toml").write_text("""[tui]
master_width = 40
""")

    app = CocliApp(auto_show=False)

    async with app.run_test() as driver:

        # Wait for initial on_mount
        await driver.pause(0.5)
        
        # Act
        await driver.press("space")
        await driver.pause(0.1)
        await driver.press("a")
        await driver.pause(0.1)
        
        # Navigate to Campaigns category (index 0 in app_nav_list)
        application_view = await wait_for_widget(driver, ApplicationView)
        nav_list = application_view.query_one("#app_nav_list", ListView)
        
        # Ensure it is focused and index is 0
        nav_list.focus()
        nav_list.index = 0
        
        # We need to actually select it to trigger the switch
        # If enter fails, let's try direct method call for test stability
        nav_list.action_select_cursor()
        await driver.pause(0.5) # Wait for it to mount
        
        await wait_for_widget(driver, CampaignSelection)

        # Assert - Check that MasterDetailView has a Horizontal layout internally
        master_detail = app.query_one(MasterDetailView)
        assert len(master_detail.query("Horizontal")) == 1
        
        # Check width from config was applied (it might be on the MasterDetailView instance)
        assert master_detail.master_width == 40
