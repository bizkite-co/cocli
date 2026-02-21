# POLICY: frictionless-data-policy-enforcement (See docs/FRICTIONLESS_DATA_POLICY_ENFORCEMENT.md)
from typing import Any, Dict, Optional, TYPE_CHECKING, cast
import logging
import asyncio
from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal, VerticalScroll
from textual.widgets import Label, ListView, ListItem, Static
from textual import work
from rich.table import Table

from cocli.models.campaigns.queues.metadata import QUEUES_METADATA, QueueMetadata, PropertyInfo
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
                yield Label("pending/", classes="panel-header-green")
                yield Label("", id="from_model_label", classes="model-name-label")
                yield Label("PENDING COUNT: 0", id="count_pending_label", classes="count-display-label")
                yield Vertical(id="source_props_list", classes="panel-content")
            
            # RIGHT: Destination / Completed
            with Vertical(classes="panel", id="dest_panel"):
                yield Label("completed/", classes="panel-header-green")
                yield Label("", id="to_model_label", classes="model-name-label")
                yield Label("COMPLETED COUNT: 0", id="count_completed_label", classes="count-display-label")
                yield Vertical(id="dest_props_list", classes="panel-content")

    def update_detail(self, queue_id: str) -> None:
        meta = QUEUES_METADATA.get(queue_id)
        if not meta:
            return
        
        self.active_queue = meta
        self.query_one("#queue_title", Label).update(f"QUEUE: {meta.label.upper()}")
        
        # Set Model Names
        self.query_one("#from_model_label", Label).update(meta.from_model_name)
        self.query_one("#to_model_label", Label).update(meta.to_model_name)
        
        # 1. Populate Property Lists (Left/Right)
        self._populate_props("#source_props_list", meta.from_property_map, "cyan")
        self._populate_props("#dest_props_list", meta.to_property_map, "magenta")
        
        # 2. Refresh counts and info
        self.refresh_counts()

    def _populate_props(self, container_id: str, props: Dict[str, PropertyInfo], color: str) -> None:
        """
        Populates a vertical list of properties into the container.
        Format: {name}:{type} {desc}
        """
        container = self.query_one(container_id, Vertical)
        container.remove_children()
        
        tech_names = []
        for tech_name, info in props.items():
            # Technical name in bold color
            # Type and description follow on the same line.
            line = f"[bold {color}]{tech_name}[/]:[dim]{info.type}[/] {info.desc}"
            name_label = Label(line, classes="prop-line")
            # Store tech name for test verification
            setattr(name_label, "tech_name", tech_name)
            container.mount(name_label)
            tech_names.append(tech_name)
        
        setattr(container, "tech_props", tech_names)

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

        # Metadata Table
        info_table = Table(box=None, show_header=False, expand=True, padding=(0, 1))
        info_table.add_column("Key", style="dim cyan", width=20)
        info_table.add_column("Value", style="white")
        
        metadata = {
            "Functional Purpose": self.active_queue.description,
            "Task Model": self.active_queue.model_class.__name__,
            "Filesystem Path": f"[bold green]{display_path_str}[/]",
            "Sharding Strategy": self.active_queue.sharding_strategy,
            "Upstream Sources": ", ".join(self.active_queue.from_models),
            "Downstream Targets": ", ".join(self.active_queue.to_models)
        }

        for key, val in metadata.items():
            info_table.add_row(key, val)
        
        widget = self.query_one("#queue_info_content", Static)
        widget.update(info_table)
        setattr(widget, "metadata_map", metadata)

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
