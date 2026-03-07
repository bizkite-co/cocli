from typing import Any, TYPE_CHECKING, cast, Dict, Optional
import logging
import asyncio
from datetime import datetime
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll, Horizontal, Vertical
from textual.widgets import Label, ListView, ListItem, Static, Input, LoadingIndicator
from textual.message import Message
from textual.widget import Widget
from textual.binding import Binding
from textual import on, work, events

from .campaign_selection import CampaignSelection
from .campaign_detail import CampaignDetail
from .status_view import StatusView
from .cluster_view import ClusterView
from .queues_view import QueueSelection, QueueDetail
from .indexes_view import IndexSelection, IndexDetail
from .log_viewer import LogViewerModal, capture_logs
from cocli.models.campaigns.campaign import Campaign

if TYPE_CHECKING:
    from ..app import CocliApp

logger = logging.getLogger(__name__)

class ApplicationView(Container):
    """A consolidated view for Application-level tasks."""

    class CampaignActivated(Message):
        def __init__(self, campaign_name: str) -> None:
            super().__init__()
            self.campaign_name = campaign_name

    BINDINGS = [
        ("[", "focus_sidebar", "Focus Sidebar"),
        ("]", "focus_content", "Focus Content"),
        ("v", "view_full_log", "View Full Log"),
        ("ctrl+r", "run_active_operation", "Run Operation"),
        Binding("enter", "run_active_operation", "Run Operation", show=False),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.active_category: str = "operations"
        self.can_focus = True
        self.current_log_content: str = ""

    def compose(self) -> ComposeResult:
        with Horizontal():
            # Left Column: Stacked Sidebar
            with Vertical(id="app_sidebar_column"):
                with Vertical(id="app_nav_container"):
                    yield Label("[bold]Application[/bold]", classes="sidebar-title")
                    yield ListView(
                        ListItem(Label("Campaigns"), id="nav_campaigns"),
                        ListItem(Label("Cluster Dashboard"), id="nav_cluster"),
                        ListItem(Label("Environment Status"), id="nav_status"),
                        ListItem(Label("Indexes"), id="nav_indexes"),
                        ListItem(Label("Queues"), id="nav_queues"),
                        ListItem(Label("Operations"), id="nav_operations"),
                        id="app_nav_list"
                    )
                
                with Vertical(id="app_sub_nav_container"):
                    yield Label("[bold]Menu[/bold]", id="sub_sidebar_title", classes="sidebar-title")
                    yield QueueSelection(id="sidebar_queues", classes="sub-sidebar-list")
                    yield IndexSelection(id="sidebar_indexes", classes="sub-sidebar-list")
                    yield CampaignSelection(id="sidebar_campaigns", classes="sub-sidebar-list")
                    yield ListView(
                        ListItem(Label("[dim]--- Reporting ---[/dim]"), disabled=True),
                        ListItem(Label("Generate Report"), id="op_report"),
                        ListItem(Label("Analyze Emails"), id="op_analyze_emails"),
                        
                        # Sync
                        ListItem(Label("[dim]--- Data Sync ---[/dim]"), disabled=True),
                        ListItem(Label("Sync All"), id="op_sync_all"),
                        ListItem(Label("Sync GM List Queue"), id="op_sync_gm_list"),
                        ListItem(Label("Sync GM Details Queue"), id="op_sync_gm_details"),
                        ListItem(Label("Sync Enrichment Queue"), id="op_sync_enrichment"),
                        ListItem(Label("Sync Indexes"), id="op_sync_indexes"),

                        # Scaling
                        ListItem(Label("[dim]--- Cloud Scaling ---[/dim]"), disabled=True),
                        ListItem(Label("Scale to 0 (Stop)"), id="op_scale_0"),
                        ListItem(Label("Scale to 1 (Slow)"), id="op_scale_1"),
                        ListItem(Label("Scale to 5 (Standard)"), id="op_scale_5"),
                        ListItem(Label("Scale to 10 (Fast)"), id="op_scale_10"),

                        # Maintenance
                        ListItem(Label("[dim]--- Maintenance ---[/dim]"), disabled=True),
                        ListItem(Label("Compact Email Index"), id="op_compact_index"),
                        ListItem(Label("Compact Prospects"), id="op_compact_prospects"),
                        ListItem(Label("Compile Lifecycle"), id="op_compile_lifecycle"),
                        ListItem(Label("Compile To-Call List"), id="op_compile_to_call"),
                        ListItem(Label("Restore Company Names"), id="op_restore_names"),
                        ListItem(Label("Push Local Queue"), id="op_push_queue"),
                        ListItem(Label("Audit Integrity"), id="op_audit_integrity"),
                        ListItem(Label("Audit Queue"), id="op_audit_queue"),
                        ListItem(Label("Purge Pending"), id="op_purge_pending"),
                        ListItem(Label("Rollout Discovery Batch"), id="op_rollout_discovery"),
                        ListItem(Label("Cluster Path Check"), id="op_path_check"),
                        id="sidebar_operations",
                        classes="sub-sidebar-list"
                    )
            
            # Center: The main content area
            with Container(id="app_main_content"):
                yield LoadingIndicator(id="app_loading", classes="hidden")

                # Content Roots
                with VerticalScroll(id="view_operations", classes="category-content-root"):
                    with Horizontal(id="op_header_row"):
                        yield Label("Select an operation.", id="op_title", classes="op-title")
                        yield Static("", id="op_status_indicator")
                    yield Static("", id="op_description", classes="op-description")
                    yield Label("", id="op_last_run", classes="op-timestamp")
                    with Vertical(id="op_params_area"):
                        yield Label("Operation Parameters:", id="op_params_title")
                        with Horizontal(id="op_name_container"):
                            yield Label("Batch Name:", id="op_name_label")
                            yield Input(placeholder="rollout_1", id="op_name_input", value="rollout_1")
                        with Horizontal(id="op_limit_container"):
                            yield Label("Limit (Target Amount):", id="op_limit_label")
                            yield Input(placeholder="20", id="op_limit_input", value="20")
                    yield Container(id="op_content_area")
                    with VerticalScroll(id="op_log_preview_container"):
                        yield Static("", id="op_log_preview")

                with VerticalScroll(id="view_queues", classes="category-content-root"):
                    yield QueueDetail(id="queue_detail")

                with VerticalScroll(id="view_indexes", classes="category-content-root"):
                    yield IndexDetail(id="index_detail")

                with VerticalScroll(id="view_campaigns", classes="category-content-root"):
                    yield CampaignDetail(id="campaign-detail")

                yield StatusView(id="view_status", classes="category-content-root")
                yield ClusterView(id="view_cluster", classes="category-content-root")

            # Right sidebar for Recent Operations
            with Vertical(id="app_recent_runs"):
                yield Label("[bold]Recent Runs[/bold]", classes="sidebar-title")
                yield ListView(id="recent_runs_list")

    async def on_mount(self) -> None:
        from ..app import time_perf
        with time_perf("TUI: ApplicationView.on_mount"):
            self.query_one("#app_loading").display = False
            nav_list = self.query_one("#app_nav_list", ListView)
            nav_list.index = 0
            nav_list.focus()
            self.query_one("#op_params_area").display = False
            # Initial switch
            self.call_after_refresh(self.show_category, "campaigns")
            self.update_recent_runs()

    def action_focus_sidebar(self) -> None:
        self.query_one("#app_nav_list", ListView).focus()

    def action_focus_content(self) -> None:
        target = self._get_active_sidebar_widget()
        if target:
            target.focus()

    def _get_active_sidebar_widget(self) -> Optional[Widget]:
        cmap = {
            "operations": "#sidebar_operations",
            "campaigns": "#sidebar_campaigns",
            "indexes": "#sidebar_indexes",
            "queues": "#sidebar_queues"
        }
        sel = cmap.get(self.active_category)
        if sel:
            try:
                return self.query_one(sel)
            except Exception:
                return None
        return None

    def on_key(self, event: events.Key) -> None:
        focused = self.app.focused
        if not focused or isinstance(focused, Input):
            return

        if event.key == "h":
            if self.active_category in ["queues", "indexes"] and focused.id in ["queue_detail", "index_detail"]:
                sw = self._get_active_sidebar_widget()
                if sw:
                    sw.focus()
                event.stop()
                return
            if isinstance(focused, ListView) and focused.id and str(focused.id).startswith("sidebar_"):
                self.query_one("#app_nav_list", ListView).focus()
                event.stop()
                return
            # From Status/Cluster views back to Sidebar
            if focused.id in ["view_status", "view_cluster"]:
                self.query_one("#app_nav_list", ListView).focus()
                event.stop()
                return

        if isinstance(focused, ListView) and (focused.id == "app_nav_list" or (focused.id and str(focused.id).startswith("sidebar_"))):
            if event.key == "j":
                focused.action_cursor_down()
                event.prevent_default()
                event.stop()
            elif event.key == "k":
                focused.action_cursor_up()
                event.prevent_default()
                event.stop()
            elif event.key == "l" or event.key == "enter":
                if focused.id == "sidebar_operations":
                    # For operations, ENTER focuses the detail area for parameter editing
                    try:
                        self.query_one("#view_operations").focus()
                    except Exception:
                        pass
                else:
                    focused.action_select_cursor()
                event.prevent_default()
                event.stop()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle selection in any of our ListViews."""
        if event.list_view.id == "app_nav_list":
            index = event.list_view.index
            categories = ["campaigns", "cluster", "status", "indexes", "queues", "operations"]
            if index is not None and 0 <= index < len(categories):
                self.show_category(categories[index])
        elif event.list_view.id == "sidebar_operations":
            try:
                # Selection in sidebar just shifts focus to detail for editing
                self.query_one("#view_operations").focus()
            except Exception:
                pass
        elif event.list_view.id == "sidebar_queues":
            try:
                q_detail = self.app.query_one("#queue_detail", QueueDetail)
                q_detail.focus()
            except Exception:
                pass
        elif event.list_view.id == "sidebar_indexes":
            try:
                idx_detail = self.app.query_one("#index_detail", IndexDetail)
                idx_detail.focus()
            except Exception:
                pass

    def show_category(self, category: str) -> None:
        """Exclusively switch the visible content and sidebars for a category."""
        from ..app import time_perf
        with time_perf(f"TUI: ApplicationView.show_category ({category})"):
            self.active_category = category
            
            # Map categories to their sidebar and content view IDs
            category_map: Dict[str, Dict[str, Optional[str]]] = {
                "campaigns":  {"sidebar": "sidebar_campaigns",  "view": "view_campaigns"},
                "cluster":    {"sidebar": None,                 "view": "view_cluster"},
                "status":     {"sidebar": None,                 "view": "view_status"},
                "indexes":    {"sidebar": "sidebar_indexes",    "view": "view_indexes"},
                "queues":     {"sidebar": "sidebar_queues",     "view": "view_queues"},
                "operations": {"sidebar": "sidebar_operations", "view": "view_operations"}
            }

            target = category_map.get(category, {})
            target_sidebar_id = target.get("sidebar")
            target_view_id = target.get("view")

            # 1. Update Sidebars
            for sidebar in self.query(".sub-sidebar-list"):
                sidebar.display = (sidebar.id == target_sidebar_id)
            
            self.query_one("#app_sub_nav_container").display = (category not in ["status", "cluster"])

            # 2. Update Content
            main_content = self.query_one("#app_main_content")
            for child in main_content.children:
                if child.id == "app_loading":
                    continue
                child.display = (child.id == target_view_id)

            # 3. Category Specific UI Updates
            title_label = self.query_one("#sub_sidebar_title", Label)
            if category == "campaigns":
                title_label.update("[bold]Campaigns[/bold]")
                try:
                    sidebar = self.query_one("#sidebar_campaigns", ListView)
                    if sidebar.index is None and sidebar.children:
                        sidebar.index = 0
                except Exception:
                    pass
            elif category == "status":
                title_label.update("[bold]Environment[/bold]")
            elif category == "cluster":
                title_label.update("[bold]Cluster[/bold]")
            elif category == "indexes":
                title_label.update("[bold]Indexes[/bold]")
                try:
                    sidebar = self.query_one("#sidebar_indexes", ListView)
                    if sidebar.index is None and sidebar.children:
                        sidebar.index = 0
                    # Force detail update for initial selection
                    item = sidebar.highlighted_child
                    if item and item.id:
                        idx_id = str(item.id).replace("idx_", "")
                        self.app.query_one("#index_detail", IndexDetail).update_detail(idx_id)
                except Exception:
                    pass
            elif category == "operations":
                title_label.update("[bold]Operations[/bold]")
                try:
                    sidebar = self.query_one("#sidebar_operations", ListView)
                    if sidebar.index is None and sidebar.children:
                        sidebar.index = 1
                except Exception:
                    pass
            elif category == "queues":
                title_label.update("[bold]Queues[/bold]")
                try:
                    sidebar = self.query_one("#sidebar_queues", ListView)
                    if sidebar.index is None and sidebar.children:
                        sidebar.index = 0
                    # Force detail update for initial selection
                    item = sidebar.highlighted_child
                    if item and item.id:
                        q_id = str(item.id).replace("q_", "")
                        self.app.query_one("#queue_detail", QueueDetail).update_detail(q_id)
                except Exception:
                    pass
            
            def shift_focus() -> None:
                try:
                    if category in ["status", "cluster"]:
                        cv = self.app.query_one(f"#{target_view_id}")
                        cv.focus()
                    else:
                        sw = self._get_active_sidebar_widget()
                        if sw:
                            sw.focus()
                except Exception:
                    pass
            
            app = cast("CocliApp", self.app)
            if app.services.sync_search:
                shift_focus()
            else:
                self.call_after_refresh(shift_focus)

    def update_recent_runs(self) -> None:
        from ..app import time_perf
        with time_perf("TUI: ApplicationView.update_recent_runs"):
            try:
                app = cast("CocliApp", self.app)
                runs_list = self.query_one("#recent_runs_list", ListView)
                
                # Simple optimization: only rebuild if the count has changed
                if len(runs_list.children) == len(app.process_runs) and len(app.process_runs) > 0:
                    return
                
                runs_list.clear()
                for run in reversed(app.process_runs[-15:]):
                    status_color = "green" if run.status == "success" else "yellow" if run.status == "running" else "red"
                    timestamp = run.start_time.strftime("%H:%M:%S")
                    label = f"[{status_color}]{run.title}[/] [dim]({timestamp})[/]"
                    runs_list.append(ListItem(Static(label)))
            except Exception as e:
                logger.error(f"Failed to update recent runs: {e}")

    @on(ListView.Highlighted, "#sidebar_operations")
    @work(exclusive=True)
    async def handle_op_highlight(self, event: ListView.Highlighted) -> None:
        from ..app import time_perf
        if not event.item or not event.item.id:
            return
        
        # Debounce
        app = cast("CocliApp", self.app)
        if not app.services.sync_search:
            await asyncio.sleep(0.25)

        op_id = str(event.item.id)
        with time_perf(f"TUI: handle_op_highlight ({op_id})"):
            op = await asyncio.to_thread(app.services.operation_service.get_details, op_id)
            if not op:
                return
            
            try:
                self.query_one("#op_title", Label).update(op.title)
                self.query_one("#op_description", Static).update(op.description)
                params_area = self.query_one("#op_params_area", Vertical)
                params_area.display = (op_id in ["op_compile_to_call", "op_rollout_discovery"])
                self.query_one("#op_name_container").display = (op_id == "op_rollout_discovery")
                self.query_one("#op_limit_container").display = (op_id in ["op_compile_to_call", "op_rollout_discovery"])
                content_area = self.query_one("#op_content_area", Container)
                content_area.remove_children()
                self.query_one("#op_last_run", Label).update(f"Last Run: {self.get_last_run_info(op_id)}")
            except Exception as e:
                logger.error(f"Error updating op header: {e}")

    @on(ListView.Highlighted, "#sidebar_indexes")
    @work(exclusive=True)
    async def handle_index_highlight(self, event: ListView.Highlighted) -> None:
        from ..app import time_perf
        if not event.item or not event.item.id:
            return
        
        # Debounce
        app = cast("CocliApp", self.app)
        if not app.services.sync_search:
            await asyncio.sleep(0.25)

        index_id = str(event.item.id).replace("idx_", "")
        with time_perf(f"TUI: handle_index_highlight ({index_id})"):
            try:
                detail = self.app.query_one("#index_detail", IndexDetail)
                detail.update_detail(index_id)
            except Exception:
                pass

    @on(ListView.Selected, "#sidebar_indexes")
    def handle_index_selection(self, event: ListView.Selected) -> None:
        try:
            detail = self.app.query_one("#index_detail", IndexDetail)
            detail.focus()
        except Exception:
            pass

    @on(ListView.Highlighted, "#sidebar_queues")
    @work(exclusive=True)
    async def handle_queue_highlight(self, event: ListView.Highlighted) -> None:
        from ..app import time_perf
        if not event.item or not event.item.id:
            return
        
        # Debounce
        app = cast("CocliApp", self.app)
        if not app.services.sync_search:
            await asyncio.sleep(0.25)

        queue_id = str(event.item.id).replace("q_", "")
        with time_perf(f"TUI: handle_queue_highlight ({queue_id})"):
            try:
                detail = self.app.query_one("#queue_detail", QueueDetail)
                detail.update_detail(queue_id)
            except Exception:
                pass

    @on(ListView.Selected, "#sidebar_queues")
    def handle_queue_selection(self, event: ListView.Selected) -> None:
        try:
            detail = self.app.query_one("#queue_detail", QueueDetail)
            detail.focus()
        except Exception:
            pass

    def action_view_full_log(self) -> None:
        if self.current_log_content:
            focused = self.app.focused
            if isinstance(focused, ListView) and focused.id == "sidebar_operations":
                item = focused.highlighted_child
                if item and item.id:
                    op_id = str(item.id)
                    app = cast("CocliApp", self.app)
                    op = app.services.operation_service.get_details(op_id)
                    self.app.push_screen(LogViewerModal(op.title if op else "Log", self.current_log_content))

    def action_run_active_operation(self) -> None:
        """Standardized shortcut to run the operation currently highlighted in the sidebar.
        Works whether focus is in sidebar or content area.
        """
        if self.active_category == "operations":
            try:
                # Find the sidebar, even if not focused
                sidebar = self.query_one("#sidebar_operations", ListView)
                item = sidebar.highlighted_child
                if item and item.id:
                    self.run_operation(str(item.id))
            except Exception as e:
                logger.error(f"Failed to run active operation: {e}")

    def get_last_run_info(self, op_id: str) -> str:
        app = cast("CocliApp", self.app)
        runs = [r for r in app.process_runs if r.op_id == op_id and r.status == "success"]
        if runs:
            return max(runs, key=lambda r: r.start_time).start_time.strftime("%Y-%m-%d %H:%M:%S")
        return "Never"

    def log_callback(self, text: str) -> None:
        self.current_log_content += text
        try:
            preview = self.query_one("#op_log_preview", Static)
            lines = self.current_log_content.split("\n")
            preview.update("\n".join(lines[-10:]))
        except Exception:
            pass

    @work(exclusive=True, thread=True)
    async def run_operation(self, op_id: str) -> None:
        indicator = self.query_one("#op_status_indicator", Static)
        indicator.update("[bold yellow]Running...[/bold yellow]")
        self.current_log_content = ""
        app = cast("CocliApp", self.app)
        op = app.services.operation_service.get_details(op_id)
        if not op:
            return
        params: Dict[str, Any] = {}
        if op_id == "op_compile_to_call":
            try:
                params["limit"] = int(self.query_one("#op_limit_input", Input).value or 20)
            except ValueError:
                params["limit"] = 20
        elif op_id == "op_rollout_discovery":
            try:
                params["batch_name"] = self.query_one("#op_name_input", Input).value
                params["limit"] = int(self.query_one("#op_limit_input", Input).value or 50)
            except ValueError:
                params["limit"] = 50
        elif op_id == "op_purge_pending":
            # No special params needed for purge for now
            pass

        from ..navigation import ProcessRun
        run_record = ProcessRun(op_id, op.title)
        app.process_runs.append(run_record)
        self.call_after_refresh(self.update_recent_runs)

        try:
            with capture_logs(self.log_callback):
                await app.services.operation_service.execute(op_id, log_callback=self.log_callback, params=params)
            run_record.status = "success"
            indicator.update("[bold green]Success[/bold green]")
            self.app.notify(f"{op.title} Complete")
        except Exception as e:
            run_record.status = "failed"
            indicator.update("[bold red]Failed[/bold red]")
            self.app.notify(f"Error: {e}", severity="error")
        finally:
            run_record.end_time = datetime.now()
            self.call_after_refresh(self.update_recent_runs)
            self.call_after_refresh(lambda: self.app.query_one("#op_last_run", Label).update(f"Last Run: {self.get_last_run_info(op_id)}"))

    @on(CampaignSelection.CampaignSelected)
    async def handle_campaign_activation(self, message: CampaignSelection.CampaignSelected) -> None:
        try:
            campaign_name = message.campaign_name
            app = cast("CocliApp", self.app)
            if hasattr(app, "services"):
                app.services.campaign_service.campaign_name = campaign_name
                app.services.campaign_service.activate()
                self.app.notify(f"Activated Campaign: {campaign_name}")
                self.post_message(self.CampaignActivated(campaign_name))
        except Exception as e:
            self.app.notify(f"Activation Failed: {e}", severity="error")

    @on(CampaignSelection.CampaignSelected)
    async def handle_campaign_selection(self, message: CampaignSelection.CampaignSelected) -> None:
        try:
            campaign = await asyncio.to_thread(Campaign.load, message.campaign_name)
            detail = self.app.query_one("#campaign-detail", CampaignDetail)
            detail.update_detail(campaign)
            detail.focus()
        except Exception as e:
            logger.error(f"Failed to select campaign {message.campaign_name}: {e}")

    @on(CampaignSelection.CampaignHighlighted)
    @work(exclusive=True)
    async def handle_campaign_highlight(self, message: CampaignSelection.CampaignHighlighted) -> None:
        from ..app import time_perf
        
        # Debounce to prevent rapid navigation stutter
        app = cast("CocliApp", self.app)
        if not app.services.sync_search:
            await asyncio.sleep(0.25)
        
        with time_perf(f"TUI: handle_campaign_highlight ({message.campaign_name})"):
            try:
                campaign = await asyncio.to_thread(Campaign.load, message.campaign_name)
                detail = self.app.query_one("#campaign-detail", CampaignDetail)
                detail.update_detail(campaign)
            except Exception as e:
                logger.error(f"Failed to load campaign {message.campaign_name}: {e}")
                try:
                    detail = self.app.query_one("#campaign-detail", CampaignDetail)
                    detail.display_error("Error Loading Campaign", f"Invalid Campaign: {message.campaign_name}\n\n{str(e)}")
                except Exception:
                    pass
