import pytest
from cocli.tui.app import CocliApp
from cocli.tui.widgets.master_detail import MasterDetailView
from cocli.tui.widgets.campaign_selection import CampaignSelection
from cocli.tui.widgets.application_view import ApplicationView
from conftest import wait_for_widget

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
        
        # ApplicationView mounts CampaignSelection by default in master-detail
        await wait_for_widget(driver, ApplicationView)
        await wait_for_widget(driver, CampaignSelection)

        # Assert - Check that MasterDetailView has a Horizontal layout internally
        master_detail = app.query_one(MasterDetailView)
        assert len(master_detail.query("Horizontal")) == 1
        
        # Check width from config was applied (it might be on the MasterDetailView instance)
        # In cocli/tui/widgets/master_detail.py it sets self.master_width
        assert master_detail.master_width == 40
