from textual.app import ComposeResult
from textual.widgets import Label, DataTable
from textual.containers import VerticalScroll, Horizontal
from typing import Any, TYPE_CHECKING
import asyncio
from datetime import datetime, UTC

from cocli.core.gossip_bridge import bridge

if TYPE_CHECKING:
    pass

class ClusterView(VerticalScroll):
    """Real-time cluster dashboard using Gossip Bridge data."""

    BINDINGS = [
        ("R", "refresh_cluster", "Refresh Now"),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.can_focus = True

    def compose(self) -> ComposeResult:
        with Horizontal(id="cluster_header"):
            yield Label("Cluster Dashboard (Live)", id="cluster_title")
            yield Label("", id="cluster_last_updated")
        
        yield DataTable(id="cluster_table")

    def on_mount(self) -> None:
        table = self.query_one("#cluster_table", DataTable)
        table.add_columns("Node ID", "CPU Load", "Memory %", "Workers", "Active Tasks", "Last Seen")
        table.cursor_type = "row"
        
        # Start the live refresh loop
        self.run_worker(self._refresh_loop())

    async def _refresh_loop(self) -> None:
        """Background loop to update the table from GossipBridge.heartbeats."""
        while True:
            self.update_table()
            await asyncio.sleep(2) # Refresh UI every 2s

    def update_table(self) -> None:
        try:
            table = self.query_one("#cluster_table", DataTable)
        except Exception:
            # Table not mounted yet
            return
            
        table.clear()
        
        if not bridge or not bridge.heartbeats:
            # Add a placeholder if no nodes seen
            return

        now = datetime.now(UTC)
        
        for node_id, hb in sorted(bridge.heartbeats.items()):
            # Calculate freshness
            ts_str = hb.get("timestamp", "")
            freshness = "Unknown"
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    diff = (now - ts).total_seconds()
                    if diff < 15:
                        freshness = "[bold green]LIVE[/bold green]"
                    else:
                        freshness = f"[yellow]{int(diff)}s ago[/yellow]"
                except Exception:
                    pass

            table.add_row(
                node_id,
                f"{hb.get('load_avg', 0.0):.2f}",
                f"{hb.get('memory_percent', 0.0):.1f}%",
                str(hb.get("worker_count", 0)),
                str(hb.get("active_tasks", 0)),
                freshness
            )
        
        self.query_one("#cluster_last_updated", Label).update(f"Updated: {now.strftime('%H:%M:%S')}")

    def action_refresh_cluster(self) -> None:
        self.update_table()
