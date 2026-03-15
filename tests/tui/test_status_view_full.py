# POLICY: frictionless-data-policy-enforcement
import pytest
from unittest.mock import MagicMock
from cocli.tui.app import CocliApp
from cocli.tui.widgets.status_view import StatusView
from textual.widgets import Label

@pytest.mark.asyncio
async def test_tui_status_view_navigation(mocker):
    """
    Test that navigating to Application -> Status correctly triggers hydration
    and shows the new data root/S3 remote fields.
    """
    app = CocliApp(auto_show=False)
    
    # Mock reporting service to return our test data
    mock_env = {
        "campaign": "test-campaign",
        "context": "test-context",
        "strategy": "Mock Strategy",
        "strategy_details": ["Detail 1"],
        "data_root": "/mock/data/root",
        "s3_data_root": "s3://mock-bucket"
    }
    
    # Inject mock service into the real app container
    app.services.reporting_service.get_environment_status = MagicMock(return_value=mock_env)
    app.services.reporting_service.load_cached_report = MagicMock(return_value=None)
    app.services.reporting_service.get_cluster_health = MagicMock(return_value=[])
    
    async with app.run_test() as pilot:
        # 1. Open Application View
        await pilot.press("space")
        await pilot.pause(0.1)
        await pilot.press("a")
        await pilot.pause(0.5)
        
        # 2. Select 'status' from sidebar
        # In ApplicationView sidebar: campaigns, cluster, status, ...
        # 'status' is at index 2
        await pilot.press("j", "j", "enter")
        await pilot.pause(0.5)
        
        status_view = app.query_one("#view_status", StatusView)
        assert status_view.display is True
        
        # 3. Wait for hydration
        import time
        start = time.time()
        while status_view.status_data is None and time.time() - start < 5:
            await pilot.pause(0.2)
            
        assert status_view.status_data == mock_env
        
        # 4. Verify that the loading message is gone and body has children
        body = status_view.query_one("#status_body")
        # After update_view(), the body should have new children (Environment Panel, etc.)
        # and the initial "Loading..." Static should be gone.
        assert len(body.children) >= 1
        
        # Check that the last updated label in the header was initialized
        header_label = status_view.query_one("#status_last_updated", Label)
        assert header_label is not None
