from typing import Any, Dict, TYPE_CHECKING, cast
import asyncio
import logging
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll, Horizontal
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

    def compose(self) -> ComposeResult:
        # Sidebar for top-level Application categories
        with VerticalScroll(id="app_sidebar"):
            yield Label("[bold]Application[/bold]", classes="sidebar-title")
            yield ListView(
                ListItem(Label("Campaigns"), id="nav_campaigns"),
                ListItem(Label("Environment Status"), id="nav_status"),
                ListItem(Label("Operations"), id="nav_operations"),
                id="app_nav_list"
            )
        
        # The main content area
        yield Container(id="app_main_content")

    def on_mount(self) -> None:
        # Start in Operations (index 2) as requested
        nav_list = self.query_one("#app_nav_list", ListView)
        nav_list.index = 2
        nav_list.focus()
        self.show_category("operations")

    def action_focus_sidebar(self) -> None:
        self.query_one("#app_nav_list", ListView).focus()

    def action_focus_content(self) -> None:
        content = self.query_one("#app_main_content")
        for widget in content.query("*"):
            if widget.can_focus:
                widget.focus()
                break

    def action_select_item(self) -> None:
        focused = self.app.focused
        if isinstance(focused, ListView):
            focused.action_select_cursor()

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
        content = self.query_one("#app_main_content", Container)
        
        # Clear existing content safely
        content.remove_children()
        
        if category == "campaigns":
            campaign_list = CampaignSelection()
            campaign_detail = CampaignDetail(id="campaign-detail")
            detail_pane = VerticalScroll()
            
            config = get_config()
            mv = MasterDetailView(master=campaign_list, detail=detail_pane, master_width=config.tui.master_width)
            
            # Mount mv to content
            content.mount(mv)
            
            # Mount children to detail_pane AFTER mv is mounted
            def _mount_children() -> None:
                detail_pane.mount(campaign_detail)
                detail_pane.mount(Button("Activate Campaign", variant="primary", id="btn_activate_campaign"))
            
            self.call_after_refresh(_mount_children)
            
        elif category == "status":
            content.mount(StatusView())
            
        elif category == "operations":
            content.mount(OperationsMenu())

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
                # Use CampaignService to activate
                app = cast("CocliApp", self.app)
                if hasattr(app, "services"):
                    app.services.campaign_service.campaign_name = campaign_name
                    app.services.campaign_service.activate()
                    self.post_message(self.CampaignActivated(campaign_name))
        except Exception as e:
            self.app.notify(f"Activation Failed: {e}", severity="error")

class OperationsMenu(Container):
    """A menu for ETL/Sync/Audit operations with non-blocking execution and details."""

    BINDINGS = [
        ("[", "focus_sidebar", "Focus Sidebar"),
        ("]", "focus_detail", "Focus Detail"),
        ("v", "view_full_log", "View Full Log"),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.current_log_content: str = ""

    def compose(self) -> ComposeResult:
        with Horizontal():
            with VerticalScroll(id="ops_sidebar"):
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
            with VerticalScroll(id="ops_detail"):
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

    def on_mount(self) -> None:
        self.query_one("#ops_list", ListView).focus()
        self.query_one("#btn_view_log").display = False

    def action_focus_sidebar(self) -> None:
        self.query_one("#ops_list", ListView).focus()

    def action_focus_detail(self) -> None:
        self.query_one("#btn_run_op", Button).focus()

    def action_view_full_log(self) -> None:
        if self.current_log_content:
            highlighted = self.query_one("#ops_list", ListView).highlighted_child
            if highlighted and highlighted.id:
                op_id = str(highlighted.id)
                title = self.get_op_details(op_id)["title"]
                self.app.push_screen(LogViewerModal(title, self.current_log_content))

    @on(Button.Pressed, "#btn_view_log")
    def handle_view_log_btn(self) -> None:
        self.action_view_full_log()

    def on_key(self, event: events.Key) -> None:
        """Handle vim-like navigation for the operations list."""
        list_view = self.query_one("#ops_list", ListView)
        if event.key == "j":
            list_view.action_cursor_down()
            event.prevent_default()
        elif event.key == "k":
            list_view.action_cursor_up()
            event.prevent_default()
        elif event.key == "l" or event.key == "enter":
            if list_view.has_focus:
                list_view.action_select_cursor()
                event.prevent_default()

    @on(ListView.Highlighted, "#ops_list")
    def handle_op_highlight(self, event: ListView.Highlighted) -> None:
        if not event.item or not event.item.id:
            return
        
        op_id = str(event.item.id)
        details = self.get_op_details(op_id)
        
        self.query_one("#op_title", Label).update(details["title"])
        self.query_one("#op_description", Static).update(details["description"])
        
        # Update last run from cache
        last_run = self.get_last_run_info(op_id)
        self.query_one("#op_last_run", Label).update(f"Last Run: {last_run}")
        
        # Clear log preview when switching ops
        self.query_one("#op_log_preview", Static).update("")
        self.query_one("#btn_view_log").display = False

    @on(Button.Pressed, "#btn_run_op")
    def handle_run_op(self) -> None:
        ops_list = self.query_one("#ops_list", ListView)
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
        # Placeholder: in a real impl, we'd read from a local JSON state file
        return "Never"

    def log_callback(self, text: str) -> None:
        """Callback for real-time log streaming."""
        self.current_log_content += text
        # Keep preview short
        preview = self.query_one("#op_log_preview", Static)
        lines = self.current_log_content.split("\n")
        preview.update("\n".join(lines[-10:]))

    @work(exclusive=True, thread=True)
    async def run_operation(self, op_id: str) -> None:
        indicator = self.query_one("#op_status_indicator", Static)
        indicator.update("[bold yellow]Running...[/bold yellow]")
        self.query_one("#btn_view_log").display = True
        self.current_log_content = ""
        
        app = cast("CocliApp", self.app)
        services = app.services
        
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
            
            indicator.update("[bold green]Success[/bold green]")
            self.app.notify("Operation Complete")
        except Exception as e:
            indicator.update("[bold red]Failed[/bold red]")
            self.app.notify(f"Error: {e}", severity="error")
            print(f"CRITICAL ERROR: {e}") # Captured by capture_logs
