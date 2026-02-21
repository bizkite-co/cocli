import pytest
from textual.app import App, ComposeResult
from textual.widgets import Label
from cocli.tui.widgets.queues_view import QueueDetail

class SimpleQueueApp(App):
    """A minimal app to test the QueueDetail widget in isolation."""
    def compose(self) -> ComposeResult:
        yield QueueDetail(id="queue_detail")

@pytest.mark.asyncio
async def test_queue_detail_layout_verified(mocker):
    """
    Verify QueueDetail structure:
    - Metadata top
    - Pending (Left) / Completed (Right)
    - Counts at top of columns
    - sp/sc bindings
    """
    app = SimpleQueueApp()
    
    async with app.run_test():
        detail = app.query_one("#queue_detail", QueueDetail)
        
        # 1. Verify basic sections exist
        assert detail.query_one("#queue_info_panel")
        assert detail.query_one("#queue_transform_grid")
        assert detail.query_one("#source_panel")
        assert detail.query_one("#dest_panel")
        
        # 2. Verify Count Labels exist
        assert detail.query_one("#count_pending_label", Label)
        assert detail.query_one("#count_completed_label", Label)
        
        # 3. Verify Structural Order (Count above Table)
        source_panel = detail.query_one("#source_panel")
        # Children: 0:Header, 1:CountLabel, 2:PropsTable
        assert source_panel.children[1].id == "count_pending_label"
        assert source_panel.children[2].id == "source_props_table"
        
        dest_panel = detail.query_one("#dest_panel")
        assert dest_panel.children[1].id == "count_completed_label"
        assert dest_panel.children[2].id == "dest_props_table"

        # 4. Verify Bindings (Literal sequences)
        # Check class BINDINGS
        binding_keys = [b[0] for b in QueueDetail.BINDINGS]
        assert "s p" in binding_keys
        assert "s c" in binding_keys
        
        binding_descriptions = [b[2] for b in QueueDetail.BINDINGS]
        assert "Sync Pending (sp)" in binding_descriptions
        assert "Sync Completed (sc)" in binding_descriptions
