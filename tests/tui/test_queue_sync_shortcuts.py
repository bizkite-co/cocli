# POLICY: frictionless-data-policy-enforcement
import pytest
from textual.widgets import ListView
from cocli.tui.app import CocliApp
from cocli.tui.widgets.queues_view import QueueSelection, QueueDetail

@pytest.mark.asyncio
async def test_queue_sync_shortcuts(mocker):
    """
    Verifies that 'sp' and 'sc' shortcuts in QueueDetail trigger sync.
    """
    from tests.conftest import wait_for_widget
    mock_sync = mocker.patch("cocli.application.data_sync_service.DataSyncService.sync_queues")
    mocker.patch("cocli.application.reporting_service.ReportingService.get_campaign_stats")
    
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        # Manually show application view
        await app.action_show_application()
        
        # Wait for the ApplicationView and nav list to appear
        nav_list = await wait_for_widget(pilot, ListView, "#app_nav_list")
        nav_list.index = 3 # Queues
        await pilot.press("enter")
        
        # Wait for queues view
        queue_list = await wait_for_widget(pilot, QueueSelection, "#app_queue_list")
        queue_list.index = 0
        await pilot.press("enter")
        
        # Wait for detail view
        detail = await wait_for_widget(pilot, QueueDetail)
        assert app.focused == detail
        
        # Test 's' then 'p' (Sync Pending)
        await pilot.press("s")
        await pilot.press("p")
        await pilot.pause()
        assert mock_sync.called
        
        # Test 's' then 'c' (Sync Completed)
        mock_sync.reset_mock()
        await pilot.press("s")
        await pilot.press("c")
        await pilot.pause()
        assert mock_sync.called

if __name__ == "__main__":
    import subprocess
    subprocess.run(["pytest", "-s", __file__])
