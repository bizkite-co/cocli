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
    mock_sync = mocker.patch("cocli.application.data_sync_service.DataSyncService.sync_queues")
    mocker.patch("cocli.application.reporting_service.ReportingService.get_campaign_stats")
    
    app = CocliApp()
    async with app.run_test() as pilot:
        await pilot.press("space", "a")
        await pilot.pause()
        
        nav_list = app.query_one("#app_nav_list", ListView)
        nav_list.index = 3 # Queues
        await pilot.press("enter")
        await pilot.pause()
        
        queue_list = app.query_one("#app_queue_list", QueueSelection)
        queue_list.index = 0
        await pilot.press("enter")
        await pilot.pause()
        
        detail = app.query_one(QueueDetail)
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
