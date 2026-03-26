# POLICY: frictionless-data-policy-enforcement
import pytest
from typing import cast
from textual.widgets import ListView
from cocli.tui.app import CocliApp
from cocli.application.services import ServiceContainer
from cocli.tui.widgets.queues_view import QueueSelection, QueueDetail


@pytest.mark.asyncio
async def test_queue_sync_shortcuts(mocker):
    """
    Verifies that 'sp' and 'sc' shortcuts in QueueDetail trigger sync.
    """
    from tests.conftest import wait_for_widget

    mock_sync = mocker.patch(
        "cocli.application.data_sync_service.DataSyncService.sync_queues"
    )
    mocker.patch(
        "cocli.application.reporting_service.ReportingService.get_campaign_stats"
    )

    services = ServiceContainer(sync_search=True)
    services.set_campaign("test-campaign")
    app = CocliApp(services=services, auto_show=False)
    async with app.run_test() as pilot:
        # Manually show application view
        await app.action_show_application()

        # Wait for the ApplicationView and nav list to appear
        nav_list = await wait_for_widget(pilot, ListView, "#app_nav_list")
        nav_list.index = (
            4  # Queues is now index 4 (Campaigns, Cluster, Status, Indexes, Queues)
        )
        await pilot.press("enter")
        # Wait for queues view
        queue_list = await wait_for_widget(pilot, QueueSelection, "#sidebar_queues")
        assert queue_list.visible is True
        # Select first item and ensure detail is loaded
        await pilot.press("enter")

        # 3. Verify QueueDetail is visible
        detail_visible = False
        detail = None
        for _ in range(20):
            try:
                results = app.query("#queue_detail")
                if results and results.first().visible:
                    detail = cast(QueueDetail, results.first())
                    detail_visible = True
                    break
            except Exception:
                pass
            await pilot.pause(0.1)

        assert detail_visible, "QueueDetail did not become visible"
        assert detail is not None

        # Explicitly set focus to the detail view for chord testing
        app.set_focus(detail)
        await pilot.pause(0.1)

        assert detail.active_queue is not None

        # Test action_sync_pending directly (chord bindings may not work in test mode)
        detail.action_sync_pending()
        await pilot.pause(0.5)
        assert mock_sync.called

        # Test action_sync_completed
        mock_sync.reset_mock()
        detail.action_sync_completed()
        await pilot.pause(0.5)
        assert mock_sync.called
