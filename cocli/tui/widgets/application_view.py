from typing import Any, Dict, List, Optional, TYPE_CHECKING, cast
import asyncio
import logging
from datetime import datetime
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll, Horizontal, Vertical
from textual.widgets import Label, ListView, ListItem, Static, Button
from textual.message import Message
from textual import on, work, events

from .master_detail import MasterDetailView
from .campaign_selection import CampaignSelection
from .campaign_detail import CampaignDetail
from .status_view import StatusView
from .log_viewer import LogViewerModal, capture_logs
from cocli.models.campaign import Campaign
from cocli.core.config import get_config

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
        ("l", "select_item", "Select"),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.active_category: str = "operations"
        self.can_focus = True

    def compose(self) -> ComposeResult:
        with Horizontal():
            # Left Column: Stacked Sidebar
            with Vertical(id="app_sidebar_column"):
                # Top level Application menu
                with Vertical(id="app_nav_container"):
                    yield Label("[bold]Application[/bold]", classes="sidebar-title")
                    yield ListView(
                        ListItem(Label("Campaigns"), id="nav_campaigns"),
                        ListItem(Label("Environment Status"), id="nav_status"),
                        ListItem(Label("Operations"), id="nav_operations"),
                        id="app_nav_list"
                    )
                
                # Dynamic Sub-menu (List portion of category)
                with Vertical(id="app_sub_nav_container"):
                    yield Label("[bold]Menu[/bold]", id="sub_sidebar_title", classes="sidebar-title")
                    yield Container(id="app_sub_sidebar")
            
            # Center: The main content / detail area
            yield Container(id="app_main_content")

            # Right sidebar for Recent Operations
            with Vertical(id="app_recent_runs"):
                yield Label("[bold]Recent Runs[/bold]", classes="sidebar-title")
                yield ListView(id="recent_runs_list")

    def on_mount(self) -> None:
        # Start in Operations (index 2)
        nav_list = self.query_one("#app_nav_list", ListView)
        nav_list.index = 2
        nav_list.focus()
        self.show_category("operations")
        self.update_recent_runs()

    def action_reset_view(self) -> None:
        """Move focus back to the main navigation list."""
        self.query_one("#app_nav_list", ListView).focus()

    def action_focus_sidebar(self) -> None:
        self.query_one("#app_nav_list", ListView).focus()

    def action_focus_content(self) -> None:
        # Try to focus the sub-menu if it's visible, otherwise main content
        sub_sidebar = self.query_one("#app_sub_sidebar")
        focusable = sub_sidebar.query("ListView, Button, Input")
        if focusable:
            focusable.first().focus()
        else:
            content = self.query_one("#app_main_content")
            for widget in content.query("*"):
                if widget.can_focus:
                    widget.focus()
                    break

    def action_select_item(self) -> None:
        focused = self.app.focused
        if isinstance(focused, ListView):
            focused.action_select_cursor()

    def on_key(self, event: events.Key) -> None:
        """Handle sidebar navigation keys."""
        nav_list = self.query_one("#app_nav_list", ListView)
        if nav_list.has_focus:
            if event.key == "j":
                nav_list.action_cursor_down()
                event.prevent_default()
            elif event.key == "k":
                nav_list.action_cursor_up()
                event.prevent_default()
            elif event.key == "l" or event.key == "enter":
                nav_list.action_select_cursor()
                event.prevent_default()

    @on(ListView.Selected, "#app_nav_list")
    def handle_nav_selection(self, event: ListView.Selected) -> None:
        if event.item.id == "nav_campaigns":
            self.show_category("campaigns")
        elif event.item.id == "nav_status":
            self.show_category("status")
        elif event.item.id == "nav_operations":
            self.show_category("operations")

    def show_category(self, category: str) -> None:
        logger.debug(f"show_category: {category}")
        self.active_category = category
        
        sub_sidebar = self.query_one("#app_sub_sidebar", Container)
        content = self.query_one("#app_main_content", Container)
        
        sub_sidebar.remove_children()
        content.remove_children()
        
        title_label = self.query_one("#sub_sidebar_title", Label)
        
        if category == "campaigns":
            title_label.update("[bold]Campaigns[/bold]")
            campaign_list = CampaignSelection()
            campaign_detail = CampaignDetail(id="campaign-detail")
            
            sub_sidebar.mount(campaign_list)
            content.mount(campaign_detail)
            content.mount(Button("Activate Campaign", variant="primary", id="btn_activate_campaign"))
            
        elif category == "status":
            title_label.update("[bold]Environment[/bold]")
            content.mount(StatusView())
            
        elif category == "operations":
            title_label.update("[bold]Operations[/bold]")
            ops_menu = OperationsMenu()
            # We don't mount the menu itself if we want to split it
            # Instead, we mount its specific parts
            sub_sidebar.mount(ops_menu.query_one("#ops_list"))
            content.mount(ops_menu.query_one("#ops_detail_container"))

    def update_recent_runs(self) -> None:
        """Update the list of recent process runs."""
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

    @on(CampaignSelection.CampaignSelected)
    def handle_campaign_highlight(self, message: CampaignSelection.CampaignSelected) -> None:
        """Update the detail pane when a campaign is highlighted in the list."""
        try:
            detail = self.query_one("#campaign-detail", CampaignDetail)
            campaign = Campaign.load(message.campaign_name)
            detail.update_detail(campaign)
        except Exception:
            pass

    @on(Button.Pressed, "#btn_activate_campaign")
    async def handle_activate_campaign(self) -> None:
        try:
            detail = self.query_one("#campaign-detail", CampaignDetail)
            if detail.campaign:
                campaign_name = detail.campaign.name
                app = cast("CocliApp", self.app)
                if hasattr(app, "services"):
                    app.services.campaign_service.campaign_name = campaign_name
                    app.services.campaign_service.activate()
                    self.post_message(self.CampaignActivated(campaign_name))
        except Exception as e:
            self.app.notify(f"Activation Failed: {e}", severity="error")

class OperationsMenu(Container):
    """
    A helper widget that provides the operations components.
    Note: These are extracted by ApplicationView for its stacked layout.
    """
    def compose(self) -> ComposeResult:
        # This structure allows extraction of the list and detail
        yield ListView(
            # Reporting
            ListItem(Label("[dim]--- Reporting ---[/dim]"), disabled=True),
            ListItem(Label("Generate Report"), id="op_report"),
            ListItem(Label("Analyze Emails"), id="op_analyze_emails"),

            # Sync
            ListItem(Label("[dim]--- Data Sync ---[/dim]"), disabled=True),
            ListItem(Label("Sync All (S3->Local)"), id="op_sync_all"),
            ListItem(Label("Push Queue to S3"), id="op_push_queue"),

            # Audit
            ListItem(Label("[dim]--- Audit ---[/dim]"), disabled=True),
            ListItem(Label("Audit Integrity"), id="op_audit_integrity"),
            ListItem(Label("Audit Queue"), id="op_audit_queue"),
            
            id="ops_list"
        )
        with VerticalScroll(id="ops_detail_container"):
            yield Label("Select an operation to see details.", id="op_title", classes="op-title")
            yield Static("", id="op_description", classes="op-description")
            yield Label("", id="op_last_run", classes="op-timestamp")
            yield Horizontal(
                Button("Run Operation", variant="primary", id="btn_run_op"),
                Button("View Full Log", id="btn_view_log"),
                Static("", id="op_status_indicator"),
                id="op_actions"
            )
            with VerticalScroll(id="op_log_preview_container"):
                yield Static("", id="op_log_preview")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.current_log_content: str = ""

    def on_mount(self) -> None:
        try:
            self.query_one("#btn_view_log").display = False
        except Exception:
            pass

    def action_view_full_log(self) -> None:
        if self.current_log_content:
            highlighted = self.app.query_one("#ops_list", ListView).highlighted_child
            if highlighted and highlighted.id:
                op_id = str(highlighted.id)
                title = self.get_op_details(op_id)["title"]
                self.app.push_screen(LogViewerModal(title, self.current_log_content))

    @on(Button.Pressed, "#btn_view_log")
    def handle_view_log_btn(self) -> None:
        self.action_view_full_log()

    @on(ListView.Highlighted, "#ops_list")
    def handle_op_highlight(self, event: ListView.Highlighted) -> None:
        if not event.item or not event.item.id:
            return
        
        op_id = str(event.item.id)
        details = self.get_op_details(op_id)
        
        self.app.query_one("#op_title", Label).update(details["title"])
        self.app.query_one("#op_description", Static).update(details["description"])
        
        # Update last run from cache
        last_run = self.get_last_run_info(op_id)
        self.app.query_one("#op_last_run", Label).update(f"Last Run: {last_run}")
        
        # Clear log preview when switching ops
        self.app.query_one("#op_log_preview", Static).update("")
        self.app.query_one("#btn_view_log").display = False

    @on(Button.Pressed, "#btn_run_op")
    def handle_run_op(self) -> None:
        ops_list = self.app.query_one("#ops_list", ListView)
        highlighted = ops_list.highlighted_child
        if highlighted and highlighted.id:
            op_id = str(highlighted.id)
            self.run_operation(op_id)

    def get_op_details(self, op_id: str) -> Dict[str, str]:
        details = {
            "op_report": {
                "title": "Campaign Report",
                "description": "Generates a full data funnel report, including prospect counts, queue depths, and worker distribution. Results are cached locally."
            },
            "op_analyze_emails": {
                "title": "Email Analysis",
                "description": "Performs deep validation of found emails, checking for domain validity and common patterns."
            },
            "op_sync_all": {
                "title": "Full S3 Sync",
                "description": "Synchronizes all campaign data (prospects, emails, indexes) from S3 to your local machine."
            },
            "op_push_queue": {
                "title": "Push Enrichment Queue",
                "description": "Uploads locally generated enrichment tasks to the global S3 queue for workers to process."
            },
            "op_audit_integrity": {
                "title": "Audit Campaign Integrity",
                "description": "Scans for cross-contamination between campaigns and unauthorized keywords."
            },
            "op_audit_queue": {
                "title": "Audit Queue Completion",
                "description": "Verifies that all 'completed' markers in the queue actually have corresponding records in the index."
            }
        }
        return details.get(op_id, {"title": "Unknown", "description": "No description available."})

    def get_last_run_info(self, op_id: str) -> str:
        """Detect last run time from memory or disk cache."""
        from ..app import CocliApp
        app = cast(CocliApp, self.app)
        
        # 1. Check in-memory session runs first
        runs = [r for r in app.process_runs if r.op_id == op_id and r.status == "success"]
        if runs:
            latest = max(runs, key=lambda r: r.start_time)
            return latest.start_time.strftime("%Y-%m-%d %H:%M:%S")

        # 2. Check disk cache for reports
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
        """Callback for real-time log streaming."""
        self.current_log_content += text
        preview = self.app.query_one("#op_log_preview", Static)
        lines = self.current_log_content.split("\n")
        preview.update("\n".join(lines[-10:]))

    @work(exclusive=True, thread=True)
    async def run_operation(self, op_id: str) -> None:
        indicator = self.app.query_one("#op_status_indicator", Static)
        indicator.update("[bold yellow]Running...[/bold yellow]")
        self.app.query_one("#btn_view_log").display = True
        self.current_log_content = ""
        
        from ..app import CocliApp
        app = cast(CocliApp, self.app)
        services = app.services
        
        # Log to recent runs
        title = self.get_op_details(op_id)["title"]
        from ..navigation import ProcessRun
        run_record = ProcessRun(op_id, title)
        app.process_runs.append(run_record)
        
        # Trigger UI update for recent runs
        try:
            parent_view = next((a for a in self.ancestors if isinstance(a, ApplicationView)), None)
            if parent_view:
                parent_view.call_after_refresh(parent_view.update_recent_runs)
        except Exception:
            pass

        try:
            with capture_logs(self.log_callback):
                if op_id == "op_report":
                    await asyncio.to_thread(services.reporting_service.get_campaign_stats)
                elif op_id == "op_sync_all":
                    await asyncio.to_thread(services.data_sync_service.sync_all)
                elif op_id == "op_push_queue":
                    await asyncio.to_thread(services.data_sync_service.push_queue)
                elif op_id == "op_audit_integrity":
                    await asyncio.to_thread(services.audit_service.audit_campaign_integrity)
                elif op_id == "op_audit_queue":
                    await asyncio.to_thread(services.audit_service.audit_queue_completion)
                elif op_id == "op_analyze_emails":
                    await asyncio.to_thread(services.reporting_service.get_email_analysis)
            
            run_record.status = "success"
            indicator.update("[bold green]Success[/bold green]")
            self.app.notify(f"{title} Complete")
        except Exception as e:
            run_record.status = "failed"
            indicator.update("[bold red]Failed[/bold red]")
            self.app.notify(f"Error: {e}", severity="error")
            print(f"CRITICAL ERROR: {e}") # Captured by capture_logs
        finally:
            run_record.end_time = datetime.now()
            # Update UI again
            try:
                if parent_view:
                    parent_view.call_after_refresh(parent_view.update_recent_runs)
                
                def refresh_last_run() -> None:
                    try:
                        self.app.query_one("#op_last_run", Label).update(f"Last Run: {self.get_last_run_info(op_id)}")
                    except Exception:
                        pass
                self.call_after_refresh(refresh_last_run)
            except Exception:
                pass
