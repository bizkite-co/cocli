import pytest
from textual.widgets import DataTable
from cocli.tui.widgets.cluster_view import ClusterView
from cocli.core.gossip_bridge import bridge
from unittest.mock import patch
from datetime import datetime, UTC

@pytest.mark.asyncio
async def test_cluster_view_population():
    """
    Verifies that ClusterView correctly populates the DataTable 
    from GossipBridge heartbeats.
    """
    # Mock data
    mock_heartbeats = {
        "node-1": {
            "node_id": "node-1",
            "load_avg": 1.25,
            "memory_percent": 45.5,
            "worker_count": 3,
            "active_tasks": 1,
            "timestamp": datetime.now(UTC).isoformat()
        },
        "node-2": {
            "node_id": "node-2",
            "load_avg": 0.5,
            "memory_percent": 20.0,
            "worker_count": 5,
            "active_tasks": 0,
            "timestamp": datetime.now(UTC).isoformat()
        }
    }

    # Patch the global bridge instance's heartbeats
    with patch.object(bridge, 'heartbeats', mock_heartbeats):
        view = ClusterView()
        from textual.app import App, ComposeResult
        
        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield view
        
        app = TestApp()
        async with app.run_test():
            # Trigger table update
            view.update_table()
            
            table = view.query_one(DataTable)
            
            # Verify row count
            assert len(table.rows) == 2
            
            # Verify data in first row (node-1)
            # Row 0, Col 0: Node ID
            assert table.get_cell_at((0, 0)) == "node-1"
            # Row 0, Col 1: CPU Load (formatted to 2 decimals)
            assert table.get_cell_at((0, 1)) == "1.25"
            # Row 0, Col 2: Memory %
            assert table.get_cell_at((0, 2)) == "45.5%"
            
            # Verify data in second row (node-2)
            assert table.get_cell_at((1, 0)) == "node-2"
            assert table.get_cell_at((1, 1)) == "0.50"
            
            # Verify 'LIVE' status
            assert "LIVE" in str(table.get_cell_at((0, 5)))
