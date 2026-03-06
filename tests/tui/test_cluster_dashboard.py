import pytest
from cocli.tui.app import CocliApp
from cocli.tui.widgets.cluster_view import ClusterView
from conftest import wait_for_widget

@pytest.mark.asyncio
async def test_cluster_dashboard_navigation(mock_cocli_env):
    """Test that navigating to the Cluster Dashboard displays the ClusterView."""
    app = CocliApp()
    
    async with app.run_test() as driver:
        # 1. Open Application Menu (space + a)
        await driver.press("space", "a")
        await driver.pause(0.5)
        
        # 2. Navigate to 'Cluster Dashboard' in the sidebar
        # The sidebar is a ListView. Index 0 is 'Campaigns', Index 1 is 'Cluster Dashboard'
        await driver.press("j") # Move to Cluster Dashboard
        await driver.pause(0.2)
        await driver.press("enter")
        await driver.pause(0.5)
        
        # 3. Verify ClusterView is visible
        cluster_view = await wait_for_widget(driver, ClusterView, selector="#cluster_view_root")
        assert cluster_view.display is True
        assert cluster_view.visible is True
        
        # 4. Check for expected headers
        headers = cluster_view.query("Label")
        header_texts = [str(h.render()) for h in headers]
        assert "Live Status (Gossip)" in header_texts
        assert "S3 Cluster Registry (Persistent)" in header_texts
