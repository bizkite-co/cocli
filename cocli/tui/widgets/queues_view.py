from typing import Any, Optional, TYPE_CHECKING, cast
import logging
import asyncio
from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Label, ListView, ListItem, Static
from textual import work
from rich.text import Text

from cocli.models.campaigns.queues.metadata import QUEUES_METADATA, QueueMetadata

if TYPE_CHECKING:
    from ..app import CocliApp

logger = logging.getLogger(__name__)

class QueueSelection(ListView):
    """Sidebar list for selecting a queue to view."""
    def compose(self) -> ComposeResult:
        for q_id, meta in QUEUES_METADATA.items():
            yield ListItem(Label(meta.label), id=f"q_{q_id}")

class QueueDetail(Container):
    """Detailed view for a specific queue using a panel-based transformation layout."""
    
    BINDINGS = [
        ("s", "sync_pending", "Sync Pending"),
        ("p", "sync_pending", "Sync Pending"), # Allow s or p
        ("c", "sync_completed", "Sync Completed"),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.active_queue: Optional[QueueMetadata] = None
        self.can_focus = True

    def compose(self) -> ComposeResult:
        with Horizontal(id="queue_header"):
            yield Label("Select a queue to view details.", id="queue_title")
            yield Label("", id="queue_counts_summary")
            yield Static("", id="queue_sync_indicator")
        
        yield Static("", id="queue_description", classes="op-description")
        
        # Transformation Grid (Style consistent with Company Details)
        with Container(id="queue_transform_grid"):
            # Left: Source Panel
            with Vertical(classes="panel", id="source_panel"):
                yield Label("FROM PROPERTY", classes="panel-header")
                yield Static(id="source_props_list", classes="props-list")
            
            # Right: Destination Panel
            with Vertical(classes="panel", id="dest_panel"):
                yield Label("TO PROPERTY", classes="panel-header")
                yield Static(id="dest_props_list", classes="props-list")

    def update_detail(self, queue_id: str) -> None:
        meta = QUEUES_METADATA.get(queue_id)
        if not meta:
            return
        
        self.active_queue = meta
        self.query_one("#queue_title", Label).update(f"QUEUE: {meta.label.upper()}")
        self.query_one("#queue_description", Static).update(meta.description)
        
        # Render Source Properties
        source_text = Text()
        for prop in meta.from_properties:
            source_text.append(f"• {prop}\n", style="cyan")
        self.query_one("#source_props_list", Static).update(source_text)
        
        # Render Destination Properties
        dest_text = Text()
        for prop in meta.to_properties:
            dest_text.append(f"• {prop}\n", style="magenta")
        self.query_one("#dest_props_list", Static).update(dest_text)
        
        # Refresh Counts
        self.refresh_counts()

    def refresh_counts(self) -> None:
        if not self.active_queue:
            return
        
        app = cast("CocliApp", self.app)
        campaign = app.services.reporting_service.campaign_name
        
        stats = app.services.reporting_service.load_cached_report(campaign, "status")
        if stats:
            q_stats = stats.get("local_queues", {}).get(self.active_queue.name, {})
            pending = q_stats.get("pending", 0)
            completed = q_stats.get("completed", 0)
            
            summary = f"[bold white]Pending:[/] [yellow]{pending}[/]  |  [bold white]Completed:[/] [green]{completed}[/]"
            self.query_one("#queue_counts_summary", Label).update(summary)

    def action_sync_pending(self) -> None:
        if self.active_queue:
            self.run_sync(self.active_queue.name, "pending")

    def action_sync_completed(self) -> None:
        if self.active_queue:
            self.run_sync(self.active_queue.name, "completed")

    @work(exclusive=True, thread=True)
    async def run_sync(self, queue_name: str, branch: str) -> None:
        app = cast("CocliApp", self.app)
        indicator = self.query_one("#queue_sync_indicator", Static)
        indicator.update(f"[bold yellow] Syncing {branch}...[/bold yellow]")
        
        try:
            await asyncio.to_thread(app.services.data_sync_service.sync_queues, queue_name)
            indicator.update(f"[bold green] {branch.title()} Synced[/bold green]")
            self.app.notify(f"Sync Complete: {queue_name} ({branch})")
            
            await asyncio.to_thread(app.services.reporting_service.get_campaign_stats)
            self.call_after_refresh(self.refresh_counts)
            
        except Exception as e:
            indicator.update(f"[bold red] Sync Failed: {e}[/bold red]")
            self.app.notify(f"Sync Failed: {e}", severity="error")
        
        await asyncio.sleep(3)
        indicator.update("")
