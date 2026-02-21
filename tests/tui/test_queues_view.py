import pytest
from textual.app import App, ComposeResult
from cocli.tui.widgets.queues_view import QueueDetail

class SimpleQueueApp(App):
    """A minimal app to test the QueueDetail widget in isolation."""
    def compose(self) -> ComposeResult:
        yield QueueDetail(id="queue_detail")

@pytest.mark.asyncio
async def test_queue_detail_verified_layout(mocker):
    """
    Verify:
    1. Pending Count is above its property list.
    2. Model names exist.
    3. technical names exist in property list labels.
    """
    app = SimpleQueueApp()
    # Mock services to avoid AttributeErrors in refresh_counts
    mock_services = mocker.Mock()
    mock_services.reporting_service.campaign_name = "test-campaign"
    mock_services.reporting_service.load_cached_report.return_value = {}
    app.services = mock_services
    
    async with app.run_test():
        detail = app.query_one("#queue_detail", QueueDetail)
        detail.update_detail("gm-list")
        
        # 1. Check structural hierarchy
        source_panel = detail.query_one("#source_panel")
        # Children: Header(0), Model(1), Count(2), Vertical(3)
        
        # In Textual 0.x, we can check the 'id' and 'classes' to verify identity
        assert "panel-header-green" in source_panel.children[0].classes
        assert "model-name-label" in source_panel.children[1].classes
        assert "count-display-label" in source_panel.children[2].classes
        
        # 2. Check technical names exist in property list (we stored them in tech_props)
        source_list = detail.query_one("#source_props_list")
        prop_names = getattr(source_list, "tech_props", [])
        assert "queries" in prop_names
        
        # 3. Check Bindings (sp/sc)
        binding_keys = [b[0] for b in QueueDetail.BINDINGS]
        assert "s p" in binding_keys
        assert "s c" in binding_keys
