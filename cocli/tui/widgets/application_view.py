from typing import Any, TYPE_CHECKING, cast
import logging
from datetime import datetime
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll, Horizontal, Vertical
from textual.widgets import Label, ListView, ListItem, Static
from textual.message import Message
from textual import on, work, events
from rich.table import Table
from rich.panel import Panel

from .campaign_selection import CampaignSelection
from .campaign_detail import CampaignDetail
from .status_view import StatusView
from .log_viewer import LogViewerModal, capture_logs
from cocli.models.campaign import Campaign

if TYPE_CHECKING:
    from ..app import CocliApp

logger = logging.getLogger(__name__)

class ApplicationView(Container):
    """A consolidated view for Application-level tasks (Campaigns, Status, Operations)."""

    class CampaignActivated(Message):
        def __init__(self, campaign_name: str) -> None:
            super().__init__()
            self.campaign_name = campaign_name

    BINDINGS = [
        ("[", "focus_sidebar", "Focus Sidebar"),
        ("]", "focus_content", "Focus Content"),
        ("v", "view_full_log", "View Full Log"),
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
                # 1. Top level Application menu
                with Vertical(id="app_nav_container"):
                    yield Label("[bold]Application[/bold]", classes="sidebar-title")
                    yield ListView(
                        ListItem(Label("Campaigns"), id="nav_campaigns"),
                        ListItem(Label("Environment Status"), id="nav_status"),
                        ListItem(Label("Operations"), id="nav_operations"),
                        id="app_nav_list"
                    )
                
                # 2. Sub-level list (Visible underneath)
                with Vertical(id="app_sub_nav_container"):
                    yield Label("[bold]Menu[/bold]", id="sub_sidebar_title", classes="sidebar-title")
                    
                    # Operations List
                    yield ListView(
                        # Reporting
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
                        ListItem(Label("Compact Index"), id="op_compact_index"),
                        ListItem(Label("Push Local Queue"), id="op_push_queue"),
                        ListItem(Label("Audit Integrity"), id="op_audit_integrity"),
                        ListItem(Label("Audit Queue"), id="op_audit_queue"),
                        id="ops_list",
                        classes="sub-sidebar-list"
                    )
                    
                    yield CampaignSelection(id="app_campaign_list", classes="sub-sidebar-list")
            
            # Center: The main content area
            with Container(id="app_main_content"):
                # Operations Detail
                with VerticalScroll(id="ops_detail_root", classes="category-content-root"):
                    with Horizontal(id="op_header_row"):
                        yield Label("Select an operation.", id="op_title", classes="op-title")
                        yield Static("", id="op_status_indicator")
                    
                    yield Static("", id="op_description", classes="op-description")
                    yield Label("", id="op_last_run", classes="op-timestamp")
                    
                    # Area for report content or operation output
                    yield Container(id="op_content_area")
                    
                    with VerticalScroll(id="op_log_preview_container"):
                        yield Static("", id="op_log_preview")

                # Campaign Detail
                with VerticalScroll(id="campaign_detail_root", classes="category-content-root"):
                    yield CampaignDetail(id="campaign-detail")

                # Status View
                yield StatusView(id="status_view_root", classes="category-content-root")

            # Right sidebar for Recent Operations
            with Vertical(id="app_recent_runs"):
                yield Label("[bold]Recent Runs[/bold]", classes="sidebar-title")
                yield ListView(id="recent_runs_list")

    def on_mount(self) -> None:
        nav_list = self.query_one("#app_nav_list", ListView)
        nav_list.index = 2
        nav_list.focus()
        self.show_category("operations")
        self.update_recent_runs()

    def action_reset_view(self) -> None:
        self.query_one("#app_nav_list", ListView).focus()

    def action_focus_sidebar(self) -> None:
        self.query_one("#app_nav_list", ListView).focus()

    def action_focus_content(self) -> None:
        if self.active_category == "operations":
            self.query_one("#ops_list", ListView).focus()
        elif self.active_category == "campaigns":
            self.query_one("#app_campaign_list", CampaignSelection).focus()
        elif self.active_category == "status":
            self.query_one("#status_view_root", StatusView).focus()

    def on_key(self, event: events.Key) -> None:
        """Handle sidebar navigation keys."""
        focused = self.app.focused
        if isinstance(focused, ListView) and (focused.id == "app_nav_list" or focused.id == "ops_list" or focused.id == "campaign_list_view"):
            if event.key == "j":
                focused.action_cursor_down()
                event.prevent_default()
            elif event.key == "k":
                focused.action_cursor_up()
                event.prevent_default()
            elif event.key == "l" or event.key == "enter":
                focused.action_select_cursor()
                event.prevent_default()

    @on(ListView.Selected, "#app_nav_list")
    def handle_nav_selection(self, event: ListView.Selected) -> None:
        if event.item.id == "nav_campaigns":
            self.show_category("campaigns")
            self.query_one("#app_campaign_list", CampaignSelection).focus()
        elif event.item.id == "nav_status":
            self.show_category("status")
            self.query_one("#status_view_root", StatusView).focus()
        elif event.item.id == "nav_operations":
            self.show_category("operations")
            self.query_one("#ops_list", ListView).focus()

    @on(ListView.Selected, "#ops_list")
    def handle_op_execution(self, event: ListView.Selected) -> None:
        """Triggers the operation when ENTER or l is pressed in the sub-list."""
        if event.item and event.item.id:
            self.run_operation(str(event.item.id))

    def show_category(self, category: str) -> None:
        self.active_category = category
        title_label = self.query_one("#sub_sidebar_title", Label)
        
        # Toggle Sidebar Visibility
        ops_list = self.query_one("#ops_list")
        campaign_list = self.query_one("#app_campaign_list")
        
        ops_list.display = (category == "operations")
        campaign_list.display = (category == "campaigns")
        self.query_one("#app_sub_nav_container").display = (category != "status")

        # Toggle Content Visibility
        self.query_one("#ops_detail_root").display = (category == "operations")
        self.query_one("#campaign_detail_root").display = (category == "campaigns")
        self.query_one("#status_view_root").display = (category == "status")

        if category == "campaigns":
            title_label.update("[bold]Campaigns[/bold]")
        elif category == "status":
            title_label.update("[bold]Environment[/bold]")
        elif category == "operations":
            title_label.update("[bold]Operations[/bold]")

    def update_recent_runs(self) -> None:
        try:
            app = cast("CocliApp", self.app)
            runs_list = self.query_one("#recent_runs_list", ListView)
            runs_list.clear()
            
            for run in reversed(app.process_runs[-15:]):
                status_color = "green" if run.status == "success" else "yellow" if run.status == "running" else "red"
                timestamp = run.start_time.strftime("%H:%M:%S")
                label = f"[{status_color}]{run.title}[/] [dim]({timestamp})[/]"
                runs_list.append(ListItem(Static(label)))
        except Exception:
            pass

    @on(ListView.Highlighted, "#ops_list")
    def handle_op_highlight(self, event: ListView.Highlighted) -> None:
        if not event.item or not event.item.id:
            return
        
        op_id = str(event.item.id)
        app = cast("CocliApp", self.app)
        op = app.services.operation_service.get_details(op_id)
        if not op:
            return
        
        # 1. Update Header Info
        try:
            self.query_one("#op_title", Label).update(op.title)
            self.query_one("#op_description", Static).update(op.description)
            self.query_one("#op_last_run", Label).update(f"Last Run: {self.get_last_run_info(op_id)}")
            self.query_one("#op_log_preview", Static).update("")
        except Exception:
            pass

        # 2. Update Content Area
        content_area = self.query_one("#op_content_area", Container)
        content_area.remove_children()
        
        campaign = app.services.reporting_service.campaign_name
        
        if op_id == "op_report":
            cached = app.services.reporting_service.load_cached_report(campaign, "status")
            if cached and not cached.get("error"):
                table = Table(title=f"Full Report: {campaign}", expand=True)
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="magenta")
                
                table.add_row("Total Prospects", str(cached.get("prospects_count", 0)))
                table.add_row("Enriched (S3/Global)", str(cached.get("total_enriched_global", 0)))
                table.add_row("Local Enriched", str(cached.get("enriched_count", 0)))
                table.add_row("Local Emails", str(cached.get("emails_found_count", 0)))
                
                # Add queue stats if available
                q_data = cached.get("s3_queues") or cached.get("local_queues", {})
                for q_name, metrics in q_data.items():
                    table.add_row(f"Queue: {q_name}", f"P:{metrics.get('pending',0)} I:{metrics.get('inflight',0)} C:{metrics.get('completed',0)}")
                
                content_area.mount(Static(Panel(table, border_style="green")))
        
        elif "op_scale_" in op_id:
            cached = app.services.reporting_service.load_cached_report(campaign, "status")
            if cached:
                active = cached.get("active_fargate_tasks", "Unknown")
                content_area.mount(Static(Panel(f"Current Running Tasks: [bold green]{active}[/]", title="Cloud Status")))

    def action_view_full_log(self) -> None:
        if self.current_log_content:
            focused = self.app.focused
            if isinstance(focused, ListView) and focused.id == "ops_list":
                highlighted = focused.highlighted_child
                if highlighted and highlighted.id:
                    op_id = str(highlighted.id)
                    app = cast("CocliApp", self.app)
                    op = app.services.operation_service.get_details(op_id)
                    title = op.title if op else "Log"
                    self.app.push_screen(LogViewerModal(title, self.current_log_content))

    def get_last_run_info(self, op_id: str) -> str:
        app = cast("CocliApp", self.app)
        runs = [r for r in app.process_runs if r.op_id == op_id and r.status == "success"]
        if runs:
            latest = max(runs, key=lambda r: r.start_time)
            return latest.start_time.strftime("%Y-%m-%d %H:%M:%S")

        if op_id == "op_report":
            campaign = app.services.reporting_service.campaign_name
            cached = app.services.reporting_service.load_cached_report(campaign, "status")
            if cached and cached.get("last_updated"):
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(cached["last_updated"])
                    return dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    return str(cached["last_updated"])
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

        from ..navigation import ProcessRun
        run_record = ProcessRun(op_id, op.title)
        app.process_runs.append(run_record)
        self.call_after_refresh(self.update_recent_runs)

        try:
            with capture_logs(self.log_callback):
                await app.services.operation_service.execute(op_id)
            
            run_record.status = "success"
            indicator.update("[bold green]Success[/bold green]")
            self.app.notify(f"{op.title} Complete")
        except Exception as e:
            run_record.status = "failed"
            indicator.update("[bold red]Failed[/bold red]")
            self.app.notify(f"Error: {e}", severity="error")
            print(f"CRITICAL ERROR: {e}") 
        finally:
            run_record.end_time = datetime.now()
            self.call_after_refresh(self.update_recent_runs)
            def refresh_last_run() -> None:
                try:
                    self.query_one("#op_last_run", Label).update(f"Last Run: {self.get_last_run_info(op_id)}")
                except Exception:
                    pass
            self.call_after_refresh(refresh_last_run)

    @on(CampaignSelection.CampaignSelected)
    async def handle_campaign_activation(self, message: CampaignSelection.CampaignSelected) -> None:
        """Triggered by ENTER/l in the Campaign sub-sidebar."""
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

    @on(CampaignSelection.CampaignHighlighted)
    def handle_campaign_highlight(self, message: CampaignSelection.CampaignHighlighted) -> None:
        """Update detail pane on highlight (browsing)."""
        try:
            detail = self.query_one("#campaign-detail", CampaignDetail)
            campaign = Campaign.load(message.campaign_name)
            detail.update_detail(campaign)
        except Exception:
            pass
