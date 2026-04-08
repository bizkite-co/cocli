from typing import Any, Dict, Optional, TYPE_CHECKING, cast
import logging
import asyncio
import webbrowser
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.widgets import Label, ListView, ListItem, Static, Input
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


def tui_debug_log(msg: str) -> None:
    """Lazy import to avoid circular import."""
    from cocli.tui.app import tui_debug_log as _tui_debug_log

    _tui_debug_log(msg)


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
        # Handle inline edit save/cancel
        if self.is_editing:
            if event.key == "enter":
                self._save_inline_edit()
                event.prevent_default()
                return
            if event.key == "escape":
                self._cancel_inline_edit()
                event.prevent_default()
                return

        # Audit keys for gm-list
        if self.active_queue and self.active_queue.name == "gm-list":
            if event.key == "a":
                self.action_run_audit()
                event.prevent_default()
                return
            if event.key == "r":
                self.load_audit_results()
                self.app.notify("Audit results refreshed.")
                event.prevent_default()
                return
            if event.key == "l":
                self.action_mark_reviewed()
                event.prevent_default()
                return
            if event.key == "g":
                asyncio.create_task(self.action_open_audit_gmb())
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
                event.prevent_default()
                return

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.active_queue: Optional[QueueMetadata] = None
        self.can_focus = True
        self.audit_items: list[dict[str, str]] = []
        self.audit_selected_idx: int = 0
        self.is_editing: bool = False
        self._edit_rating_input: Optional[Input] = None
        self._edit_reviews_input: Optional[Input] = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="queue_header"):
            yield Label("[dim]Admin >[/dim] [yellow]Queues[/yellow]", id="queue_title")
            yield Static("", id="queue_sync_indicator")

        # 1. Top Section: Queue Metadata Panel
        with Vertical(classes="panel", id="queue_info_panel"):
            yield Label("QUEUE METADATA", classes="panel-header")
            yield Static(id="queue_info_content", classes="panel-content")

        # 2. Middle Section: Transformation Columns (Side-by-Side)
        yield Label("[dim]Transform:[/]", classes="panel-header")
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
                "AUDIT RESULTS (a=run audit, r=refresh, l=reviewed, g=open url)",
                classes="panel-header-yellow",
            )
            with Horizontal(id="audit_headers"):
                yield Label(
                    "Source: Loading...", id="audit_source_label", classes="dim"
                )
                yield Label(
                    "Output: Loading...", id="audit_output_label", classes="dim"
                )
                yield Label("Count: Loading...", id="audit_count_label", classes="dim")
                yield Label("j/k=navigate, l=reviewed", id="audit_status")
            yield Vertical(id="audit_results_content", classes="panel-content")

    def update_detail(self, queue_id: str) -> None:
        tui_debug_log(f"update_detail called for queue: {queue_id}")
        meta = QUEUES_METADATA.get(queue_id)
        if not meta:
            tui_debug_log(f"No metadata for {queue_id}")
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

        # 3. Audit results are loaded on-demand via 'r' key (was auto-load, removed for performance)

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
        tui_debug_log(
            f"refresh_counts: campaign={campaign}, queue={self.active_queue.name if self.active_queue else 'None'}"
        )
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
    @work(exclusive=True)
    async def action_run_audit(self) -> None:
        """Run gm-list audit."""
        tui_debug_log(f"action_run_audit: active_queue={self.active_queue}")
        if not self.active_queue or self.active_queue.name != "gm-list":
            tui_debug_log("action_run_audit: not gm-list")
            return

        self.app.notify("Running audit for gm-list...")

        try:
            campaign = cast(
                "CocliApp", self.app
            ).services.reporting_service.campaign_name

            import sys

            # Use the currently running python executable to call cocli as a module
            # This is safer than relying on PATH
            cmd = [
                sys.executable,
                "-m",
                "cocli.main",
                "audit",
                "gm-list-html",
                "--campaign",
                campaign,
            ]
            tui_debug_log(f"action_run_audit: Executing {' '.join(cmd)}")

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            tui_debug_log(f"action_run_audit: stdout={stdout.decode()}")
            tui_debug_log(f"action_run_audit: stderr={stderr.decode()}")

            if proc.returncode == 0:
                self.app.notify("Audit completed successfully.")
                self.load_audit_results()
            else:
                logger.error(f"Audit failed: {stderr.decode()}")
                self.app.notify(
                    f"Audit failed: {stderr.decode()[:50]}", severity="error"
                )

        except Exception as e:
            logger.error(f"Error running audit: {e}", exc_info=True)
            self.app.notify(f"Error running audit: {e}", severity="error")

    def _get_reviewed_data(self) -> dict[str, tuple[str, str]]:
        """Read gm_list_reviewed.usv and return dict keyed by place_id with (rating, reviews)."""
        reviewed_data: dict[str, tuple[str, str]] = {}
        try:
            campaign = cast(
                "CocliApp", self.app
            ).services.reporting_service.campaign_name
            reviewed_path = (
                paths.campaign(campaign).queue("gm-list").completed
                / "audit"
                / "gm_list_reviewed.usv"
            )
            if reviewed_path.exists():
                with open(reviewed_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            parts = line.strip().split("\x1f")
                            if len(parts) >= 3:
                                pid = parts[0]
                                rating = str(parts[1]) if parts[1] else "-"
                                reviews = str(parts[2]) if parts[2] else "-"
                                reviewed_data[pid] = (rating, reviews)
        except Exception as e:
            logger.error(f"Error reading reviewed data: {e}")
        return reviewed_data

    def action_mark_reviewed(self) -> None:
        """Toggle inline editing for selected audit item."""
        if not self.active_queue or self.active_queue.name != "gm-list":
            tui_debug_log("mark_reviewed: not active gm-list queue")
            return
        if not self.audit_items:
            tui_debug_log(
                f"mark_reviewed: no audit items (count={len(self.audit_items) if self.audit_items else 'None'}, idx={self.audit_selected_idx})"
            )
            self.app.notify("No audit data. Run audit first.")
            return
        if self.audit_selected_idx >= len(self.audit_items):
            tui_debug_log(
                f"mark_reviewed: index out of range (idx={self.audit_selected_idx}, len={len(self.audit_items)})"
            )
            self.app.notify("No audit item selected.")
            return

        self.is_editing = not self.is_editing
        tui_debug_log(
            f"[EDIT START] idx={self.audit_selected_idx} is_editing={self.is_editing} row={self._get_row_text(self.audit_selected_idx)}"
        )
        self._render_audit_items()
        tui_debug_log(f"[EDIT AFTER RENDER] is_editing={self.is_editing}")

        if self.is_editing and self._edit_rating_input:
            self._edit_rating_input.focus()

    def _on_review_dialog_complete(self, result: Optional[dict[str, Any]]) -> None:
        """Callback when the review dialog closes."""
        if result is None:
            app = cast("CocliApp", self.app)
            app.nav_manager.restore_focus()
            try:
                self.query_one("#audit_results_content", Vertical).focus()
            except Exception:
                pass
            return

        rating = result.get("rating", "-")
        reviews = result.get("reviews", "-")

        if not rating or not reviews:
            self.app.notify("Rating and reviews are required.", severity="error")
            return

        idx = self.audit_selected_idx
        item = self.audit_items[idx]
        place_id = item.get("place_id", "")
        biz_name = item.get("name", "Unknown")

        try:
            from cocli.models.campaigns.indexes.gm_list_reviewed_item import (
                GmListReviewedItem,
            )

            campaign = cast(
                "CocliApp", self.app
            ).services.reporting_service.campaign_name
            reviewed_path = (
                paths.campaign(campaign).queue("gm-list").completed
                / "audit"
                / "gm_list_reviewed.usv"
            )
            reviewed_path.parent.mkdir(parents=True, exist_ok=True)

            rating_val = float(rating) if rating != "-" else 0.0
            reviews_val = int(reviews) if reviews != "-" else 0

            reviewed_item = GmListReviewedItem.create(
                place_id=place_id,
                average_rating=rating_val,
                reviews_count=reviews_val,
            )

            # Write header if model defines HEADER = True (first write only)
            if GmListReviewedItem.HEADER and not reviewed_path.exists():
                with open(reviewed_path, "w", encoding="utf-8") as f:
                    f.write(GmListReviewedItem.get_header())

            with open(reviewed_path, "a", encoding="utf-8") as f:
                f.write(reviewed_item.to_usv())

            self.app.notify(f"Reviewed: {biz_name[:30]} | {rating} ({reviews})")
            saved_idx = self.audit_selected_idx
            self.load_audit_results()
            if saved_idx < len(self.audit_items):
                self.audit_selected_idx = saved_idx
                self._render_audit_items()

            cast("CocliApp", self.app).nav_manager.restore_focus()
        except Exception as e:
            logger.error(f"mark_reviewed error: {e}")
            self.app.notify(f"Error: {e}", severity="error")

    async def action_open_audit_gmb(self) -> None:
        """Open gmb_url in browser using system browser (same as Company Details)."""
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

            gmb_url = None
            with open(audit_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip() and line.startswith(place_id + "\x1f"):
                        parts = line.strip().split("\x1f")
                        if len(parts) >= 5:
                            gmb_url = parts[4]
                            break

            if not gmb_url:
                self.app.notify("No URL found.")
                return

            self.app.notify(f"Opening: {selected_item.get('name', 'Google Maps')}")

            webbrowser.open(gmb_url)

        except Exception as e:
            self.app.notify(f"Error: {e}", severity="error")

    def load_audit_results(self) -> None:
        """Load and display audit results for gm-list."""
        tui_debug_log(
            f"load_audit_results: active_queue={self.active_queue.name if self.active_queue else 'None'}"
        )
        if not self.active_queue or self.active_queue.name != "gm-list":
            return

        try:
            campaign = cast(
                "CocliApp", self.app
            ).services.reporting_service.campaign_name
            tui_debug_log(f"load_audit_results: campaign={campaign}")

            # Source: raw HTML files
            raw_dir = paths.campaign(campaign).path / "raw" / "gm-list"
            html_count = 0
            if raw_dir.exists():
                html_files = list(raw_dir.rglob("*.html"))
                html_count = len(html_files)

            # Try to show relative path
            try:
                raw_display = f"data/{raw_dir.relative_to(paths.root)}/*.html"
            except ValueError:
                raw_display = str(raw_dir)

            self.query_one("#audit_source_label", Label).update(
                f"Source: {raw_display} ({html_count} files) "
            )

            # Output: audit results file
            audit_path = (
                paths.campaign(campaign).queue("gm-list").completed
                / "results"
                / "gm_list_audit.usv"
            )

            tui_debug_log(f"load_audit_results: Full Path={audit_path}")
            tui_debug_log(f"load_audit_results: Path Exists={audit_path.exists()}")

            # Update output label
            try:
                audit_display = f"data/{audit_path.relative_to(paths.root)}"
            except ValueError:
                audit_display = str(audit_path)
            self.query_one("#audit_output_label", Label).update(
                f"Output: {audit_display}"
            )

            container = self.query_one("#audit_results_content", Vertical)
            container.remove_children()

            if not audit_path.exists():
                tui_debug_log("load_audit_results: Path does not exist")
                self.query_one("#audit_status", Label).update(
                    f"[dim]No audit data. Path does not exist: {audit_path}[/]"
                )
                self.query_one("#audit_count_label", Label).update("Count: -")
                return

            items = []
            tui_debug_log(f"load_audit_results: Reading file {audit_path}")
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
            tui_debug_log(f"load_audit_results: Loaded {len(items)} items")

            # Update count label
            self.query_one("#audit_count_label", Label).update(
                f"Count: {len(items)} items"
            )

            if not items:
                tui_debug_log("load_audit_results: No items in file")
                self.query_one("#audit_status", Label).update(
                    "[dim]No items in audit.[/]"
                )
                return

            self.audit_items = items
            self.audit_selected_idx = 0
            self._render_audit_items()

            self.query_one("#audit_status", Label).update(
                f"[green]{len(items)} items[/] | j/k=navigate, l=reviewed"
            )

        except Exception as e:
            logger.error(f"Error loading audit: {e}", exc_info=True)
            self.query_one("#audit_status", Label).update(f"[red]Error: {e}[/]")

    def _get_row_text(self, idx: int) -> str:
        """Get the text of a row at given index for debugging."""
        if idx < 0 or idx >= len(self.audit_items):
            return f"INDEX_OUT_OF_RANGE: {idx}"
        item = self.audit_items[idx]
        name = item.get("name", "Unknown")[:40]
        rating = item.get("rating", "-")
        reviews = item.get("reviews", "-")
        return f"[{idx}] {name} | rating={rating} reviews={reviews}"

    def _render_audit_items(self) -> None:
        """Render audit items with selection highlight, reviewed status, and inline editing."""
        tui_debug_log(
            f"[RENDER] start: is_editing={self.is_editing} selected_idx={self.audit_selected_idx} total_items={len(self.audit_items)}"
        )
        container = self.query_one("#audit_results_content", Vertical)
        container.remove_children()

        reviewed_data = self._get_reviewed_data()

        header = f"{'Name':<39} {'✓':>2} {'⭐':>3} {'📋':>3}"
        container.mount(Label("[dim]" + header + "[/]"))

        for i, item in enumerate(self.audit_items):
            is_selected = i == self.audit_selected_idx
            name = item.get("name", "Unknown")
            place_id = item.get("place_id", "")
            audit_rating = item.get("rating", "-")
            audit_reviews = item.get("reviews", "-")

            is_reviewed = place_id in reviewed_data
            if is_reviewed:
                rating, reviews = reviewed_data[place_id]
                status = "[green]✓[/]"
                color = "cyan"
            elif audit_rating and audit_rating != "-":
                rating = audit_rating
                reviews = audit_reviews
                status = " "
                color = "white"
            else:
                rating = audit_rating
                reviews = audit_reviews
                status = " "
                color = "red"

            if is_selected:
                prefix = "[yellow]>[/] "
                rating_val = str(rating).rjust(0) if rating != "-" else "  -"
                reviews_val = str(reviews).rjust(4) if reviews != "-" else "  -"
                rating_input = Input(
                    value=rating_val,
                    classes="inline-input edit_rating",
                    placeholder="⭐",
                )
                reviews_input = Input(
                    value=reviews_val,
                    classes="inline-input edit_reviews",
                    placeholder="📋",
                )
                self._edit_rating_input = rating_input
                self._edit_reviews_input = reviews_input
                row = Horizontal(
                    Label(prefix + f"[{color}]{name[:38].ljust(0)}[/{color}]"),
                    Label(f" {status}"),
                    Label("  "),
                    rating_input,
                    reviews_input,
                )
                row.styles.background = "#222222"
                container.mount(row)
            else:
                prefix = " "
                line = f"{prefix}[{color}]{name:<38}[/{color}]{status}{rating:>5}{reviews:>5}"
                container.mount(Label(line))

    def _save_inline_edit(self) -> bool:
        """Save the inline edit for the selected item."""
        tui_debug_log(
            f"[SAVE EDIT] before: is_editing={self.is_editing} idx={self.audit_selected_idx}"
        )

        if (
            not self.is_editing
            or not self._edit_rating_input
            or not self._edit_reviews_input
        ):
            return False

        rating = self._edit_rating_input.value.strip()
        reviews = self._edit_reviews_input.value.strip()

        tui_debug_log(f"[SAVE EDIT] input: rating='{rating}' reviews='{reviews}'")

        if not rating or not reviews:
            self.app.notify("Rating and reviews are required.", severity="error")
            return False

        tui_debug_log("[SAVE EDIT] validated OK, saving...")
        try:
            item = self.audit_items[self.audit_selected_idx]
            place_id = item.get("place_id", "")
            biz_name = item.get("name", "Unknown")

            from cocli.models.campaigns.indexes.gm_list_reviewed_item import (
                GmListReviewedItem,
            )

            campaign = cast(
                "CocliApp", self.app
            ).services.reporting_service.campaign_name
            reviewed_path = (
                paths.campaign(campaign).queue("gm-list").completed
                / "audit"
                / "gm_list_reviewed.usv"
            )
            reviewed_path.parent.mkdir(parents=True, exist_ok=True)

            rating_val = float(rating) if rating != "-" else 0.0
            reviews_val = int(reviews) if reviews != "-" else 0

            reviewed_item = GmListReviewedItem.create(
                place_id=place_id,
                average_rating=rating_val,
                reviews_count=reviews_val,
            )

            # Write header if model defines HEADER = True (first write only)
            if GmListReviewedItem.HEADER and not reviewed_path.exists():
                with open(reviewed_path, "w", encoding="utf-8") as f:
                    f.write(GmListReviewedItem.get_header())

            with open(reviewed_path, "a", encoding="utf-8") as f:
                f.write(reviewed_item.to_usv())

            self.app.notify(f"Reviewed: {biz_name[:30]} | {rating} ({reviews})")
            self.is_editing = False
            self._render_audit_items()
            return True
        except Exception as e:
            logger.error(f"Inline save error: {e}")
            self.app.notify(f"Error: {e}", severity="error")
            return False

    def _cancel_inline_edit(self) -> None:
        """Cancel inline editing."""
        tui_debug_log(f"[CANCEL EDIT] before: is_editing={self.is_editing}")
        self.is_editing = False
        tui_debug_log("[CANCEL EDIT] after cancel, before render")
        self._render_audit_items()
        tui_debug_log(f"[CANCEL EDIT] after render, idx={self.audit_selected_idx}")

    def action_audit_down(self) -> None:
        """Move selection down in audit list."""
        if not self.audit_items:
            return
        old_idx = self.audit_selected_idx
        tui_debug_log(
            f"[NAV DOWN] before: idx={old_idx} row={self._get_row_text(old_idx)}"
        )
        self.audit_selected_idx = (self.audit_selected_idx + 1) % len(self.audit_items)
        tui_debug_log(
            f"[NAV DOWN] after: idx={self.audit_selected_idx} row={self._get_row_text(self.audit_selected_idx)}"
        )
        self._render_audit_items()
        self._scroll_to_selection()

    def action_audit_up(self) -> None:
        """Move selection up in audit list."""
        if not self.audit_items:
            return
        old_idx = self.audit_selected_idx
        tui_debug_log(
            f"[NAV UP] before: idx={old_idx} row={self._get_row_text(old_idx)}"
        )
        self.audit_selected_idx = (self.audit_selected_idx - 1) % len(self.audit_items)
        tui_debug_log(
            f"[NAV UP] after: idx={self.audit_selected_idx} row={self._get_row_text(self.audit_selected_idx)}"
        )
        self._render_audit_items()
        self._scroll_to_selection()

    def _scroll_to_selection(self) -> None:
        """Scroll the audit list to keep the current selection in view."""
        container = self.query_one("#audit_results_content", Vertical)
        try:
            children = list(container.children)
            # Header is at index 0, data items start at index 1
            item_idx = self.audit_selected_idx + 1
            if 0 < item_idx < len(children):
                selected_widget = children[item_idx]
                container.scroll_to_widget(selected_widget, animate=False)
        except Exception:
            pass
