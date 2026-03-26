from typing import Any, Dict, Optional, TYPE_CHECKING, cast
import logging
import asyncio
import webbrowser
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.widgets import Label, ListView, ListItem, Static
from textual import work, events
from rich.table import Table

from cocli.models.campaigns.queues.metadata import (
    QUEUES_METADATA,
    QueueMetadata,
    PropertyInfo,
)
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

    def on_key(self, event: events.Key) -> None:
        # Audit keys for gm-list
        if self.active_queue and self.active_queue.name == "gm-list":
            if event.key == "a":
                self.action_run_audit()
                event.prevent_default()
                return
            if event.key == "l":
                self.action_verify_item()
                event.prevent_default()
                return
            if event.key == "g":
                self.action_open_audit_gmb()
                event.prevent_default()
                return
            if event.key == "j":
                self.action_audit_down()
                event.prevent_default()
                return
            if event.key == "k":
                self.action_audit_up()
                event.prevent_default()
                return

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.active_queue: Optional[QueueMetadata] = None
        self.can_focus = True
        self.audit_items: list[dict[str, str]] = []
        self.audit_selected_idx: int = 0

    def compose(self) -> ComposeResult:
        with Horizontal(id="queue_header"):
            yield Label("[dim]Admin >[/dim] [yellow]Queues[/yellow]", id="queue_title")
            yield Static("", id="queue_sync_indicator")

        # 1. Top Section: Queue Metadata Panel
        with Vertical(classes="panel", id="queue_info_panel"):
            yield Label("QUEUE METADATA", classes="panel-header")
            yield Static(id="queue_info_content", classes="panel-content")

        # 2. Middle Section: Transformation Columns (Side-by-Side)
        with Horizontal(id="queue_transform_grid"):
            # LEFT: Source / Pending
            with Vertical(classes="panel", id="source_panel"):
                yield Label("pending/", classes="panel-header-green")
                yield Label("", id="from_model_label", classes="model-name-label")
                yield Label(
                    "PENDING COUNT: 0",
                    id="count_pending_label",
                    classes="count-display-label",
                )
                yield Vertical(id="source_props_list", classes="panel-content")

            # RIGHT: Destination / Completed
            with Vertical(classes="panel", id="dest_panel"):
                yield Label("completed/", classes="panel-header-green")
                yield Label("", id="to_model_label", classes="model-name-label")
                yield Label(
                    "COMPLETED COUNT: 0",
                    id="count_completed_label",
                    classes="count-display-label",
                )
                yield Vertical(id="dest_props_list", classes="panel-content")

        # 3. Bottom Section: Audit Results (for gm-list)
        with Vertical(classes="panel", id="audit_panel"):
            yield Label(
                "AUDIT RESULTS (a=run audit, l=verify, g=open url)",
                classes="panel-header-yellow",
            )
            yield Label("j/k=navigate, l=verify", id="audit_status")
            yield Vertical(id="audit_results_content", classes="panel-content")

    def update_detail(self, queue_id: str) -> None:
        meta = QUEUES_METADATA.get(queue_id)
        if not meta:
            return

        self.active_queue = meta
        self.query_one("#queue_title", Label).update(
            f"[dim]Admin >[/dim] [yellow]Queues[/yellow] > [green]{queue_id}[/green]"
        )

        # Set Model Names
        self.query_one("#from_model_label", Label).update(meta.from_model_name)
        self.query_one("#to_model_label", Label).update(meta.to_model_name)

        # 1. Populate Property Tables
        self._render_property_table(
            "#source_props_list", meta.from_property_map, "cyan"
        )
        self._render_property_table("#dest_props_list", meta.to_property_map, "magenta")

        # 2. Refresh counts and metadata
        self.refresh_counts()

        # 3. Auto-load audit results for gm-list
        if queue_id == "gm-list":
            self.load_audit_results()

    def _render_property_table(
        self, widget_id: str, props: Dict[str, PropertyInfo], color: str
    ) -> None:
        """Renders a vertical list of properties into a Vertical widget."""
        container = self.query_one(widget_id, Vertical)
        container.remove_children()

        tech_names = []
        for tech_name, info in props.items():
            desc = f"{info.type} {info.desc}" if hasattr(info, "desc") else str(info)
            line = f"[bold {color}]{tech_name}[/]: {desc}"
            label = Label(line, classes="prop-line")
            container.mount(label)
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

        stats = app_cast.services.reporting_service.load_cached_report(
            campaign, "status"
        )
        pending = 0
        completed = 0
        if stats:
            q_stats = stats.get("local_queues", {}).get(self.active_queue.name, {})
            pending = q_stats.get("pending", 0)
            completed = q_stats.get("completed", 0)

        # Update Count Labels
        self.query_one("#count_pending_label", Label).update(
            f"PENDING ITEMS: [bold yellow]{pending}[/]"
        )
        self.query_one("#count_completed_label", Label).update(
            f"COMPLETED ITEMS: [bold green]{completed}[/]"
        )

        # Update Metadata Table
        info_table = Table(box=None, show_header=False, expand=True, padding=(0, 1))
        info_table.add_column("Key", style="dim cyan", width=20)
        info_table.add_column("Value", style="white")

        metadata = {
            "Functional Purpose": self.active_queue.description,
            "Task Model": self.active_queue.model_class.__name__,
            "Filesystem Path": display_path_str,
            "Sharding Strategy": self.active_queue.sharding_strategy,
            "Upstream Sources": ", ".join(self.active_queue.from_models),
            "Downstream Targets": ", ".join(self.active_queue.to_models),
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
            await asyncio.to_thread(
                app.services.data_sync_service.sync_queues, queue_name
            )
            indicator.update(f"[bold green] {branch.title()} Synced[/bold green]")
            self.app.notify(f"Sync Complete: {queue_name} ({branch})")

            await asyncio.to_thread(app.services.reporting_service.get_campaign_stats)
            self.call_after_refresh(self.refresh_counts)

        except Exception as e:
            indicator.update(f"[bold red] Sync Failed: {e}[/bold red]")
            self.app.notify(f"Sync Failed: {e}", severity="error")

        await asyncio.sleep(3)
        indicator.update("")

    # Audit methods
    def action_run_audit(self) -> None:
        """Run gm-list audit."""
        if not self.active_queue or self.active_queue.name != "gm-list":
            return
        self.app.notify("Run: cocli audit gm-list-html")

    def action_verify_item(self) -> None:
        """Verify selected audit item - saves with current values."""
        if not self.active_queue or self.active_queue.name != "gm-list":
            logger.warning("verify_item: not active gm-list queue")
            return
        if not self.audit_items:
            logger.warning(
                f"verify_item: no audit items (count={len(self.audit_items) if self.audit_items else 'None'}, idx={self.audit_selected_idx})"
            )
            self.app.notify("No audit data. Run audit first.")
            return
        if self.audit_selected_idx >= len(self.audit_items):
            logger.warning(
                f"verify_item: index out of range (idx={self.audit_selected_idx}, len={len(self.audit_items)})"
            )
            self.app.notify("No audit item selected.")
            return

        # Save with current values
        idx = self.audit_selected_idx
        item = self.audit_items[idx]
        place_id = item.get("place_id", "")
        biz_name = item.get("name", "Unknown")
        rating = item.get("rating", "-")
        reviews = item.get("reviews", "-")

        logger.warning(
            f"verify_item: rating='{rating}', reviews='{reviews}', item={item}"
        )

        if not rating or not reviews or rating == "-" or reviews == "-":
            self.app.notify(
                f"No data to verify (rating='{rating}', reviews='{reviews}')",
                severity="error",
            )
            return

        try:
            from cocli.models.campaigns.indexes.gm_list_verified_item import (
                GmListVerifiedItem,
            )

            campaign = cast(
                "CocliApp", self.app
            ).services.reporting_service.campaign_name
            verified_path = (
                paths.campaign(campaign).queue("gm-list").completed
                / "results"
                / "gm_list_verified.usv"
            )
            verified_path.parent.mkdir(parents=True, exist_ok=True)

            verified_item = GmListVerifiedItem.create(
                place_id=place_id,
                average_rating=float(rating),
                reviews_count=int(reviews),
            )
            with open(verified_path, "a", encoding="utf-8") as f:
                f.write(verified_item.to_usv())

            self.app.notify(f"Verified: {biz_name[:30]} | {rating} ({reviews})")
            self.load_audit_results()
        except Exception as e:
            logger.error(f"verify_item error: {e}")
            self.app.notify(f"Error: {e}", severity="error")

    def action_open_audit_gmb(self) -> None:
        """Open gmb_url in browser."""
        if not self.active_queue or self.active_queue.name != "gm-list":
            return
        if not self.audit_items:
            self.app.notify("No audit data. Run audit first.")
            return
        if self.audit_selected_idx >= len(self.audit_items):
            self.app.notify("No audit item selected.")
            return

        try:
            campaign = cast(
                "CocliApp", self.app
            ).services.reporting_service.campaign_name
            audit_path = (
                paths.campaign(campaign).queue("gm-list").completed
                / "results"
                / "gm_list_audit.usv"
            )
            if not audit_path.exists():
                self.app.notify("No audit file.")
                return

            selected_item = self.audit_items[self.audit_selected_idx]
            place_id = selected_item.get("place_id", "")

            with open(audit_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip() and line.startswith(place_id + "\x1f"):
                        parts = line.strip().split("\x1f")
                        if len(parts) >= 5:
                            gmb_url = parts[4]
                            if gmb_url:
                                webbrowser.open(gmb_url)
                                self.app.notify(
                                    f"Opening: {selected_item.get('name', 'Google Maps')}"
                                )
                                return
            self.app.notify("No URL found.")
        except Exception as e:
            self.app.notify(f"Error: {e}", severity="error")

    def load_audit_results(self) -> None:
        """Load and display audit results for gm-list."""
        if not self.active_queue or self.active_queue.name != "gm-list":
            return

        try:
            campaign = cast(
                "CocliApp", self.app
            ).services.reporting_service.campaign_name
            audit_path = (
                paths.campaign(campaign).queue("gm-list").completed
                / "results"
                / "gm_list_audit.usv"
            )

            container = self.query_one("#audit_results_content", Vertical)
            container.remove_children()

            if not audit_path.exists():
                self.query_one("#audit_status", Label).update(
                    "[dim]No audit data. Press 'a' to run audit.[/]"
                )
                return

            items = []
            with open(audit_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        parts = line.strip().split("\x1f")
                        if len(parts) >= 5:
                            items.append(
                                {
                                    "place_id": parts[0],
                                    "name": parts[1][:40].ljust(40),
                                    "rating": parts[2].strip()
                                    if len(parts) > 2 and parts[2].strip()
                                    else "-",
                                    "reviews": parts[3].strip()
                                    if len(parts) > 3 and parts[3].strip()
                                    else "-",
                                }
                            )

            if not items:
                self.query_one("#audit_status", Label).update(
                    "[dim]No items in audit.[/]"
                )
                return

            self.audit_items = items
            self.audit_selected_idx = 0
            self._render_audit_items()

            self.query_one("#audit_status", Label).update(
                f"[green]{len(items)} items[/] | j/k=navigate, l=verify"
            )

        except Exception as e:
            logger.error(f"Error loading audit: {e}")
            self.query_one("#audit_status", Label).update(f"[red]Error: {e}[/]")

    def _render_audit_items(self) -> None:
        """Render audit items with selection highlight."""
        container = self.query_one("#audit_results_content", Vertical)
        container.remove_children()

        header = f"  {'Name':<40} {'⭐':>3} {'📋':>4}"
        container.mount(Label("[dim]" + header + "[/]"))

        for i, item in enumerate(self.audit_items):
            is_selected = i == self.audit_selected_idx
            name = item.get("name", "Unknown")
            rating = item.get("rating", "-")
            reviews = item.get("reviews", "-")

            if rating and rating != "-":
                color = "green"
            else:
                color = "red"

            if is_selected:
                prefix = "[yellow]>[/] "
            else:
                prefix = "  "

            line = f"{prefix}[{color}]{name:<40}[/{color}]{rating:>5}{reviews:>5}"
            container.mount(Label(line))

    def action_audit_down(self) -> None:
        """Move selection down in audit list."""
        if not self.audit_items:
            return
        self.audit_selected_idx = (self.audit_selected_idx + 1) % len(self.audit_items)
        self._render_audit_items()

    def action_audit_up(self) -> None:
        """Move selection up in audit list."""
        if not self.audit_items:
            return
        self.audit_selected_idx = (self.audit_selected_idx - 1) % len(self.audit_items)
        self._render_audit_items()
