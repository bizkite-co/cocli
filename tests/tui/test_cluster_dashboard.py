import pytest
from cocli.tui.app import CocliApp

@pytest.mark.asyncio
async def test_cluster_dashboard_navigation(mock_cocli_env):
    """Test that navigating to the Cluster Dashboard displays the ClusterView."""
    app = CocliApp()
    app.services.sync_search = True # Force synchronous UI updates for test reliability
    
    async with app.run_test() as driver:
        # 1. Open Application Menu (space + a)
        await driver.press("space", "a")
        await driver.pause(0.5)
        
        # 2. Navigate to 'Cluster Dashboard' in the sidebar
        # Sidebar indices: 0:Campaigns, 1:Cluster Dashboard
        await driver.press("j") 
        await driver.pause(0.2)
        await driver.press("enter")
        await driver.pause(0.5)
        
        # 3. Verify ClusterView has focus and is visible
        cluster_view = app.query_one("#view_cluster")
        assert cluster_view.visible is True
        assert app.focused == cluster_view
        
        # 4. Check for expected headers in ClusterView
        headers = cluster_view.query("Label")
        header_texts = [str(h.render()) for h in headers]
        assert "Live Status (Gossip)" in header_texts

@pytest.mark.asyncio
async def test_navigation_switching(mock_cocli_env):
    """Test switching back and forth between Status and Cluster views."""
    app = CocliApp()
    app.services.sync_search = True # Force synchronous UI updates
    
    async with app.run_test() as driver:
        await driver.press("space", "a")
        await driver.pause(0.5)
        
        # Go to Status (index 2)
        await driver.press("j", "j", "enter")
        await driver.pause(0.5)
        assert app.query_one("#view_status").visible is True
        assert app.focused == app.query_one("#view_status")
        
        # IMPORTANT: Focus must return to sidebar to navigate
        await driver.press("h") # Back to sidebar
        await driver.pause(0.2)
        
        # Go to Cluster (index 1)
        await driver.press("k", "enter")
        await driver.pause(0.5)
        assert app.query_one("#view_cluster").visible is True
        assert app.focused == app.query_one("#view_cluster")
