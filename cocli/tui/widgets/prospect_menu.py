from typing import Any, TYPE_CHECKING, cast
from textual.screen import Screen
from textual.widgets import ListView, ListItem, Label, Header, Footer
from textual.app import ComposeResult
from textual import on
from textual.containers import VerticalScroll

if TYPE_CHECKING:
    pass

class ProspectMenu(Screen[None]):
    """A screen to display Prospect options and ETL/Enrichment tasks."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("enter", "select_item", "Select"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield ListView(
                # Reporting
                ListItem(Label("[bold cyan]--- Reporting & Stats ---[/bold cyan]"), id="header_reporting", disabled=True),
                ListItem(Label("View Campaign Report"), id="report_view"),
                ListItem(Label("Analyze Emails"), id="analyze_emails"),

                # Sync
                ListItem(Label("[bold cyan]--- Data Synchronization ---[/bold cyan]"), id="header_sync", disabled=True),
                ListItem(Label("Sync All (S3 -> Local)"), id="sync_all"),
                ListItem(Label("Sync Prospects"), id="sync_prospects"),
                ListItem(Label("Sync Companies"), id="sync_companies"),
                ListItem(Label("Push Enrichment Queue to S3"), id="push_queue"),

                # Audit
                ListItem(Label("[bold cyan]--- Audit & Integrity ---[/bold cyan]"), id="header_audit", disabled=True),
                ListItem(Label("Audit Campaign Integrity"), id="audit_integrity"),
                ListItem(Label("Audit Queue Completion"), id="audit_queue"),
                ListItem(Label("Cleanup Pending Queue"), id="cleanup_pending"),

                # Cluster
                ListItem(Label("[bold cyan]--- Cluster Management (RPi) ---[/bold cyan]"), id="header_cluster", disabled=True),
                ListItem(Label("Check Cluster Health"), id="cluster_health"),
                ListItem(Label("Restart All Workers"), id="cluster_restart"),
                ListItem(Label("Stop All Workers"), id="cluster_stop"),

                # Cloud
                ListItem(Label("[bold cyan]--- Cloud Infrastructure (AWS) ---[/bold cyan]"), id="header_cloud", disabled=True),
                ListItem(Label("Scale Enrichment Service"), id="cloud_scale"),
                ListItem(Label("Deploy Infrastructure (CDK)"), id="cloud_deploy"),

                # Legacy
                ListItem(Label("[bold cyan]--- Legacy ETL ---[/bold cyan]"), id="header_legacy", disabled=True),
                ListItem(Label("Compile Enrichment"), id="compile_enrichment"),
                ListItem(Label("Enrich Websites"), id="enrich_websites"),
                ListItem(Label("Import Companies"), id="import_companies"),
                id="main_list"
            )
        yield Footer()

    def on_mount(self) -> None:
        """Focus the list on mount and skip the first header."""
        list_view = self.query_one(ListView)
        list_view.focus()
        list_view.index = 1

    @on(ListView.Selected)
    async def handle_selection(self, event: ListView.Selected) -> None:
        item_id = event.item.id
        if item_id and item_id.startswith("header_"):
            return

        from ..app import CocliApp
        app = cast(CocliApp, self.app)
        services = app.services
        
        app.notify("Executing task...")

        try:
            if item_id == "report_view":
                await self.run_task(services.reporting_service.get_campaign_stats)
                app.notify("Report generated (check logs)")
                
            elif item_id == "sync_all":
                await self.run_task(services.data_sync_service.sync_all)
                app.notify("Sync All Complete")

            elif item_id == "sync_prospects":
                await self.run_task(services.data_sync_service.sync_prospects)
                app.notify("Prospects Synced")

            elif item_id == "push_queue":
                result = await self.run_task(services.data_sync_service.push_queue)
                app.notify(f"Pushed {result.get('uploaded_count', 0)} items")

            elif item_id == "cluster_health":
                health = await self.run_task(services.worker_service.get_cluster_health)
                app.notify(f"Cluster Health: {len(health)} nodes checked")

            elif item_id == "audit_integrity":
                result = await self.run_task(services.audit_service.audit_campaign_integrity)
                app.notify(f"Audit Found {result.get('items_found', 0)} issues")

            elif item_id == "cloud_scale":
                status = services.deployment_service.get_service_status()
                new_count = 5 if status.get("running_tasks", 0) == 0 else 0
                await self.run_task(services.deployment_service.scale_service, new_count)
                app.notify(f"Scaling to {new_count}")

            else:
                app.notify("Action not yet implemented in TUI")
        except Exception as e:
            app.notify(f"Error: {str(e)}", severity="error")

    def action_cursor_down(self) -> None:
        focused = self.app.focused
        if isinstance(focused, ListView):
            focused.action_cursor_down()

    def action_cursor_up(self) -> None:
        focused = self.app.focused
        if isinstance(focused, ListView):
            focused.action_cursor_up()

    def action_select_item(self) -> None:
        focused = self.app.focused
        if isinstance(focused, ListView):
            focused.action_select_cursor()

    def run_task(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Helper to run a service method as a background task if needed, or just await it."""
        import inspect
        if inspect.iscoroutinefunction(func):
            return func(*args, **kwargs)
        else:
            return func(*args, **kwargs)
