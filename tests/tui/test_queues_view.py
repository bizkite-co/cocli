import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static
from cocli.tui.widgets.queues_view import QueueDetail

class SimpleQueueApp(App):
    """A minimal app to test the QueueDetail widget in isolation."""
    def compose(self) -> ComposeResult:
        yield QueueDetail(id="queue_detail")

@pytest.mark.asyncio
async def test_queue_detail_final_verification(mocker):
    """
    Verify:
    1. Metadata panel includes Task Model name.
    2. Pending/Completed counts are at the top of columns.
    3. Property technical names are listed below counts.
    4. sp/sc bindings are present.
    """
    # Create app and Mock services
    app = SimpleQueueApp()
    mock_services = mocker.Mock()
    mock_services.reporting_service.campaign_name = "test-campaign"
    mock_services.reporting_service.load_cached_report.return_value = {}
    app.services = mock_services
    
    async with app.run_test():
        detail = app.query_one("#queue_detail", QueueDetail)
        detail.update_detail("gm-list")
        
        # 1. Verify Metadata Table (Model Name)
        info_content = detail.query_one("#queue_info_content", Static)
        metadata = getattr(info_content, "metadata_map", {})
        assert metadata.get("Task Model") == "ScrapeTask"
        
        # 2. Check structural hierarchy
        source_panel = detail.query_one("#source_panel")
        assert source_panel.children[1].id == "count_pending_label"
        assert source_panel.children[2].id == "source_props_list"
        
        # 3. Check property names
        source_list = detail.query_one("#source_props_list")
        prop_names = getattr(source_list, "tech_props", [])
        assert "queries" in prop_names
        
        # 4. Check Bindings (sp/sc)
        binding_keys = [b[0] for b in QueueDetail.BINDINGS]
        assert "s p" in binding_keys
        assert "s c" in binding_keys
        
        binding_descriptions = [b[2] for b in QueueDetail.BINDINGS]
        assert "sp: Sync Pending" in binding_descriptions
        assert "sc: Sync Completed" in binding_descriptions
