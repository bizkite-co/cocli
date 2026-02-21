from typing import Any, Dict, Optional, TYPE_CHECKING, cast
import logging
import asyncio
from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Label, ListView, ListItem, Static
from textual import work
from rich.table import Table

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

class QueueDetail(Container):
    """
    Detailed view for a specific queue using a panel-based transformation layout.
    Maintains consistency with the Company Details view panels.
    """
    
    BINDINGS = [
        ("p", "sync_pending", "Sync Pending"),
        ("c", "sync_completed", "Sync Completed"),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.active_queue: Optional[QueueMetadata] = None
        self.can_focus = True

    def compose(self) -> ComposeResult:
        with Horizontal(id="queue_header"):
            yield Label("Select a queue to view details.", id="queue_title")
            yield Static("", id="queue_sync_indicator")
        
        # 1. Info / Status Panel (Counts, Path, Sharding)
        with Vertical(classes="panel", id="queue_info_panel"):
            yield Label("QUEUE STATUS & INFO", classes="panel-header")
            yield Static(id="queue_info_content", classes="panel-content")
        
        # 2. Transformation Grid (Source -> Destination)
        with Container(id="queue_transform_grid"):
            # Left: Source Panel
            with Vertical(classes="panel", id="source_panel"):
                yield Label("FROM (SOURCE PROPERTIES)", classes="panel-header")
                yield Static(id="source_props_table", classes="panel-content")
            
            # Right: Destination Panel
            with Vertical(classes="panel", id="dest_panel"):
                yield Label("TO (DESTINATION PROPERTIES)", classes="panel-header")
                yield Static(id="dest_props_table", classes="panel-content")

    def update_detail(self, queue_id: str) -> None:
        meta = QUEUES_METADATA.get(queue_id)
        if not meta:
            return
        
        self.active_queue = meta
        self.query_one("#queue_title", Label).update(f"QUEUE: {meta.label.upper()}")
        
        # 1. Update Transformation Tables
        self._render_property_table("#source_props_table", meta.from_property_map, "cyan")
        self._render_property_table("#dest_props_table", meta.to_property_map, "magenta")
        
        # 2. Refresh Info and Counts
        self.refresh_counts()

    def _render_property_table(self, widget_id: str, props: Dict[str, str], color: str) -> None:
        table = Table(box=None, show_header=False, expand=True, padding=(0, 1))
        table.add_column("Property", style=f"bold {color}", width=15)
        table.add_column("Description", style="white")
        
        for tech_name, desc in props.items():
            table.add_row(tech_name, desc)
        
        self.query_one(widget_id, Static).update(table)

    def refresh_counts(self) -> None:
        if not self.active_queue:
            return
        
        app = cast("CocliApp", self.app)
        campaign = app.services.reporting_service.campaign_name
        local_path = paths.campaign(campaign).queue(self.active_queue.name).path
        
        # Use relative path for display if possible, else full path
        try:
            display_path = local_path.relative_to(paths.root)
            display_path_str = f"data/{display_path}/"
        except ValueError:
            display_path_str = str(local_path)

        # Stats from cache
        stats = app.services.reporting_service.load_cached_report(campaign, "status")
        pending = 0
        completed = 0
        if stats:
            q_stats = stats.get("local_queues", {}).get(self.active_queue.name, {})
            pending = q_stats.get("pending", 0)
            completed = q_stats.get("completed", 0)
        
        # Build Info Panel Content
        info_table = Table(box=None, show_header=False, expand=True, padding=(0, 1))
        info_table.add_column("Key", style="dim cyan", width=15)
        info_table.add_column("Value", style="white")
        
        info_table.add_row("Description", self.active_queue.description)
        info_table.add_row("Data Path", display_path_str)
        info_table.add_row("Shard Strategy", self.active_queue.sharding_strategy)
        info_table.add_row("From Models", ", ".join(self.active_queue.from_models))
        info_table.add_row("To Models", ", ".join(self.active_queue.to_models))
        info_table.add_row("Pending Count", f"[bold yellow]{pending}[/]")
        info_table.add_row("Completed Count", f"[bold green]{completed}[/]")
        info_table.add_row("Controls", "[dim]Press 'p' to sync Pending, 'c' to sync Completed[/dim]")
        
        self.query_one("#queue_info_content", Static).update(info_table)

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
