from typing import Any, Dict, Optional, TYPE_CHECKING, cast
import logging
import asyncio
from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal, VerticalScroll
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

class QueueDetail(VerticalScroll):
    """
    Detailed view for a specific queue.
    Uses a vertical scrolling layout to ensure both Metadata and Property Lists
    are visible without competing for space.
    """
    
    BINDINGS = [
        ("s p", "sync_pending", "sp: Sync Pending"),
        ("s c", "sync_completed", "sc: Sync Completed"),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.active_queue: Optional[QueueMetadata] = None
        self.can_focus = True

    def compose(self) -> ComposeResult:
        with Horizontal(id="queue_header"):
            yield Label("Select a queue to view details.", id="queue_title")
            yield Static("", id="queue_sync_indicator")
        
        # 1. Top Section: Queue Metadata Panel
        with Vertical(classes="panel", id="queue_info_panel"):
            yield Label("QUEUE METADATA", classes="panel-header")
            yield Static(id="queue_info_content", classes="panel-content")
        
        # 2. Middle Section: Transformation Columns (Side-by-Side)
        with Container(id="queue_transform_grid"):
            # LEFT: Source / Pending
            with Vertical(classes="panel", id="source_panel"):
                yield Label("SOURCE (FROM-MODEL)", classes="panel-header")
                yield Label("PENDING COUNT: 0", id="count_pending_label", classes="count-display-label")
                yield VerticalScroll(id="source_props_list", classes="panel-content")
            
            # RIGHT: Destination / Completed
            with Vertical(classes="panel", id="dest_panel"):
                yield Label("DESTINATION (TO-MODEL)", classes="panel-header")
                yield Label("COMPLETED COUNT: 0", id="count_completed_label", classes="count-display-label")
                yield VerticalScroll(id="dest_props_list", classes="panel-content")

    def update_detail(self, queue_id: str) -> None:
        meta = QUEUES_METADATA.get(queue_id)
        if not meta:
            return
        
        self.active_queue = meta
        self.query_one("#queue_title", Label).update(f"QUEUE: {meta.label.upper()}")
        
        # 1. Clear and Populate Property Lists (Left/Right)
        self._populate_props("#source_props_list", meta.from_property_map, "cyan")
        self._populate_props("#dest_props_list", meta.to_property_map, "magenta")
        
        # 2. Refresh counts and info
        self.refresh_counts()

    def _populate_props(self, container_id: str, props: Dict[str, str], color: str) -> None:
        """Populates a vertical list of properties into the scrollable area."""
        container = self.query_one(container_id, VerticalScroll)
        container.remove_children()
        
        for tech_name, description in props.items():
            # Technical name in bold color
            name_label = Label(f"[bold {color}]{tech_name}[/]", classes="prop-name")
            # Store tech name for test verification
            setattr(name_label, "tech_name", tech_name)
            container.mount(name_label)
            # Description underneath
            container.mount(Label(f"{description}", classes="prop-desc"))
            container.mount(Static("", classes="prop-spacer"))

    def refresh_counts(self) -> None:
        if not self.active_queue:
            return
        
        app = self.app
        if not hasattr(app, "services"):
            return

        app_cast = cast("CocliApp", app)
        campaign = app_cast.services.reporting_service.campaign_name
        local_path = paths.campaign(campaign).queue(self.active_queue.name).path
        
        try:
            display_path = local_path.relative_to(paths.root)
            display_path_str = f"data/{display_path}/"
        except ValueError:
            display_path_str = str(local_path)

        stats = app_cast.services.reporting_service.load_cached_report(campaign, "status")
        pending = 0
        completed = 0
        if stats:
            q_stats = stats.get("local_queues", {}).get(self.active_queue.name, {})
            pending = q_stats.get("pending", 0)
            completed = q_stats.get("completed", 0)
        
        # Update Count Labels
        self.query_one("#count_pending_label", Label).update(f"PENDING ITEMS: [bold yellow]{pending}[/]")
        self.query_one("#count_completed_label", Label).update(f"COMPLETED ITEMS: [bold green]{completed}[/]")

        # Update Metadata Table
        info_table = Table(box=None, show_header=False, expand=True, padding=(0, 1))
        info_table.add_column("Key", style="dim cyan", width=20)
        info_table.add_column("Value", style="white")
        
        info_table.add_row("Functional Purpose", self.active_queue.description)
        info_table.add_row("Filesystem Path", display_path_str)
        info_table.add_row("Sharding Strategy", self.active_queue.sharding_strategy)
        info_table.add_row("Upstream Sources", ", ".join(self.active_queue.from_models))
        info_table.add_row("Downstream Targets", ", ".join(self.active_queue.to_models))
        
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
