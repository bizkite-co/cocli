from typing import Any, Optional, TYPE_CHECKING, cast
import logging
import asyncio
from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal, VerticalScroll
from textual.widgets import Label, ListView, ListItem, Static, Button
from textual import on, work
from rich.table import Table
from rich.panel import Panel

from cocli.models.campaigns.queues.metadata import QUEUES_METADATA, QueueMetadata
from cocli.core.paths import paths

if TYPE_CHECKING:
    from ..app import CocliApp

logger = logging.getLogger(__name__)

class QueueSelection(ListView):
    """Sidebar list for selecting a queue to view."""
    def compose(self) -> ComposeResult:
        for q_id, meta in QUEUES_METADATA.items():
            yield ListItem(Label(meta.label), id=f"q_{q_id}")

class QueueDetail(VerticalScroll):
    """Detailed view for a specific queue."""
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.active_queue: Optional[QueueMetadata] = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="queue_header"):
            yield Label("Select a queue to view details.", id="queue_title")
            yield Static("", id="queue_sync_indicator")
        
        yield Static("", id="queue_description", classes="op-description")
        
        with Container(id="queue_content_area"):
            # Metadata Table
            yield Static(id="queue_meta_pane")
            
            # Counts & Actions
            with Horizontal(id="queue_action_row"):
                with Vertical(classes="count-box"):
                    yield Label("PENDING", classes="count-label")
                    yield Label("0", id="count_pending", classes="count-value")
                    yield Button("Sync Pending", id="btn_sync_pending", variant="primary")
                
                with Vertical(classes="count-box"):
                    yield Label("COMPLETED", classes="count-label")
                    yield Label("0", id="count_completed", classes="count-value")
                    yield Button("Sync Completed", id="btn_sync_completed", variant="success")

    def update_detail(self, queue_id: str) -> None:
        meta = QUEUES_METADATA.get(queue_id)
        if not meta:
            return
        
        self.active_queue = meta
        self.query_one("#queue_title", Label).update(f"Queue: {meta.label}")
        self.query_one("#queue_description", Static).update(meta.description)
        
        # Render Metadata Table
        table = Table(box=None, show_header=False, expand=True)
        table.add_column("Key", style="dim cyan", width=15)
        table.add_column("Value", style="white")
        
        app = cast("CocliApp", self.app)
        campaign = app.services.reporting_service.campaign_name
        local_path = paths.campaign(campaign).queue(meta.name).path
        
        # Use relative path for display if possible, else full path
        try:
            display_path = local_path.relative_to(paths.root)
            display_path_str = f"data/{display_path}/"
        except ValueError:
            display_path_str = str(local_path)

        table.add_row("Data Path", display_path_str)
        table.add_row("From Models", ", ".join(meta.from_models))
        table.add_row("To Models", ", ".join(meta.to_models))
        table.add_row("Shard Logic", meta.sharding_strategy)
        table.add_row("Properties", ", ".join(meta.properties))
        
        self.query_one("#queue_meta_pane", Static).update(Panel(table, title="Transformation Metadata", border_style="blue"))
        
        # Refresh Counts
        self.refresh_counts()

    def refresh_counts(self) -> None:
        if not self.active_queue:
            return
        
        app = cast("CocliApp", self.app)
        campaign = app.services.reporting_service.campaign_name
        
        # Load stats from cache or trigger refresh
        stats = app.services.reporting_service.load_cached_report(campaign, "status")
        if stats:
            q_stats = stats.get("local_queues", {}).get(self.active_queue.name, {})
            self.query_one("#count_pending", Label).update(str(q_stats.get("pending", 0)))
            self.query_one("#count_completed", Label).update(str(q_stats.get("completed", 0)))

    @on(Button.Pressed, "#btn_sync_pending")
    def handle_sync_pending(self) -> None:
        if self.active_queue:
            self.run_sync(self.active_queue.name, "pending")

    @on(Button.Pressed, "#btn_sync_completed")
    def handle_sync_completed(self) -> None:
        if self.active_queue:
            self.run_sync(self.active_queue.name, "completed")

    @work(exclusive=True, thread=True)
    async def run_sync(self, queue_name: str, branch: str) -> None:
        app = cast("CocliApp", self.app)
        indicator = self.query_one("#queue_sync_indicator", Static)
        indicator.update(f"[bold yellow] Syncing {branch}...[/bold yellow]")
        
        try:
            # We'll use the existing sync service but we might need a more granular 
            # method in DataSyncService for specific branches later.
            # For now, we'll call the general queue sync.
            await asyncio.to_thread(app.services.data_sync_service.sync_queues, queue_name)
            
            indicator.update(f"[bold green] {branch.title()} Synced[/bold green]")
            self.app.notify(f"Sync Complete: {queue_name} ({branch})")
            
            # Refresh stats after sync
            await asyncio.to_thread(app.services.reporting_service.get_campaign_stats)
            self.call_after_refresh(self.refresh_counts)
            
        except Exception as e:
            indicator.update(f"[bold red] Sync Failed: {e}[/bold red]")
            self.app.notify(f"Sync Failed: {e}", severity="error")
        
        await asyncio.sleep(3)
        indicator.update("")
