import pytest
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from cocli.tui.widgets.queues_view import QueueDetail

class SimpleQueueApp(App):
    """A minimal app to test the QueueDetail widget in isolation."""
    def compose(self) -> ComposeResult:
        yield QueueDetail(id="queue_detail")

@pytest.mark.asyncio
async def test_queue_detail_structure_regression(mocker):
    """
    Verify:
    1. Pending Count is at the top of the left column.
    2. Completed Count is at the top of the right column.
    3. Property names exist in the lists below counts.
    """
    app = SimpleQueueApp()
    
    async with app.run_test():
        detail = app.query_one("#queue_detail", QueueDetail)
        detail.update_detail("gm-list")
        
        # 1. Check structural hierarchy of the panels
        source_panel = detail.query_one("#source_panel")
        # Children expected: 0:Header Label, 1:Count Label, 2:VerticalScroll List
        assert source_panel.children[1].id == "count_pending_label"
        assert source_panel.children[2].id == "source_props_list"
        
        dest_panel = detail.query_one("#dest_panel")
        assert dest_panel.children[1].id == "count_completed_label"
        assert dest_panel.children[2].id == "dest_props_list"
        
        # 2. Check technical names exist in the scroll area
        source_list = detail.query_one("#source_props_list", VerticalScroll)
        # Content is dynamic, we check the custom attribute 'tech_name'
        prop_names = [getattr(c, "tech_name") for c in source_list.children if hasattr(c, "tech_name")]
        assert "queries" in prop_names
        
        dest_list = detail.query_one("#dest_props_list", VerticalScroll)
        prop_names_dest = [getattr(c, "tech_name") for c in dest_list.children if hasattr(c, "tech_name")]
        assert "latitude" in prop_names_dest

        # 3. Check Bindings (Literals for Footer)
        binding_keys = [b[0] for b in QueueDetail.BINDINGS]
        assert "s p" in binding_keys
        assert "s c" in binding_keys
