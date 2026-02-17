from textual.app import ComposeResult
from textual.widgets import Static, Label
from textual.containers import VerticalScroll, Container, Horizontal
from textual import work
from typing import Any, Dict, Optional, List, TYPE_CHECKING, cast
import asyncio
from datetime import datetime

from cocli.renderers import status_renderer

if TYPE_CHECKING:
    from ..app import CocliApp

class StatusView(VerticalScroll):
    """A widget to display the current cocli environment status with cached data support."""

    BINDINGS = [
        ("R", "refresh_status", "Refresh Status"),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.status_data: Optional[Dict[str, Any]] = None
        self.cluster_health: List[Dict[str, Any]] = []
        self.can_focus = True

    def compose(self) -> ComposeResult:
        with Horizontal(id="status_header"):
            yield Label("Environment Status", id="status_title")
            yield Label("", id="status_last_updated")
            yield Static("", id="status_refresh_indicator")
        
        yield Container(Static("[bold yellow]Loading environment status...[/]"), id="status_body")

    def on_mount(self) -> None:
        # Spawn background hydration immediately
        self.run_worker(self.hydrate_view())

    async def hydrate_view(self) -> None:
        """Hydrate the view with initial data without blocking the UI thread."""
        app = cast("CocliApp", self.app)
        if not hasattr(app, "services"):
            return

        campaign = app.services.reporting_service.campaign_name
        
        # 1. Fetch Environment (Fast, but do it in thread just in case of I/O)
        env = await asyncio.to_thread(app.services.reporting_service.get_environment_status)
        self.status_data = env
        
        # 2. Try to load cached stats (Fast)
        cached_stats = app.services.reporting_service.load_cached_report(campaign, "status")
        if cached_stats:
            self.status_data["stats"] = cached_stats
        
        # 3. Update the UI
        self.call_after_refresh(self.update_view)

    def action_refresh_status(self) -> None:
        """Triggered by Shift+R."""
        self.trigger_refresh()

    @work(exclusive=True, thread=True)
    async def trigger_refresh(self) -> None:
        app = cast("CocliApp", self.app)
        indicator = self.query_one("#status_refresh_indicator", Static)
        indicator.update("[bold yellow] Refreshing...[/bold yellow]")
        self.app.notify("Starting environment refresh...")
        
        # Track run
        from ..navigation import ProcessRun
        run_record = ProcessRun("op_status", "Environment Refresh")
        app.process_runs.append(run_record)
        
        # Update parent sidebar if possible
        try:
            from .application_view import ApplicationView
            parent_view = next((a for a in self.ancestors if isinstance(a, ApplicationView)), None)
            if parent_view:
                parent_view.call_after_refresh(parent_view.update_recent_runs)
        except Exception:
            pass

        try:
            campaign = app.services.reporting_service.campaign_name
            
            # Fetch both stats and health in parallel
            # These are the heavy blocking calls
            stats_task = asyncio.to_thread(app.services.reporting_service.get_campaign_stats, campaign)
            health_task = app.services.reporting_service.get_cluster_health()
            
            stats, health = await asyncio.gather(stats_task, health_task)
            
            # Re-fetch environment
            env = await asyncio.to_thread(app.services.reporting_service.get_environment_status)
            env["stats"] = stats
            
            self.status_data = env
            self.cluster_health = health
            
            run_record.status = "success"
            self.call_after_refresh(self.update_view)
            indicator.update("[bold green] Done[/bold green]")
            self.app.notify("Environment refresh complete")
            await asyncio.sleep(2)
            indicator.update("")
        except Exception as e:
            run_record.status = "failed"
            indicator.update(f"[bold red] Error: {e}[/bold red]")
            self.app.notify(f"Refresh Failed: {e}", severity="error")
        finally:
            run_record.end_time = datetime.now()
            if parent_view:
                parent_view.call_after_refresh(parent_view.update_recent_runs)

    def update_view(self) -> None:
        if not self.status_data:
            return

        body = self.query_one("#status_body", Container)
        body.remove_children()
        
        # Update Timestamp in Header
        stats = self.status_data.get("stats", {})
        last_upd = stats.get("last_updated", "Never (Press R to refresh)")
        if last_upd != "Never (Press R to refresh)":
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(last_upd)
                last_upd = f"Generated: {dt.strftime('%Y-%m-%d %H:%M:%S')}"
            except Exception:
                pass
        self.query_one("#status_last_updated", Label).update(last_upd)

        # 1. Environment Panel
        body.mount(Static(status_renderer.render_environment_panel(self.status_data)))

        # 2. Cluster Health (SSH)
        if self.cluster_health:
            body.mount(Static(status_renderer.render_cluster_health_table(self.cluster_health)))

        # 3. Stats Panel
        if stats and not stats.get("error"):
            # Queues Table
            body.mount(Static(status_renderer.render_queue_table(stats)))

            # Worker Heartbeats
            hb_table = status_renderer.render_worker_heartbeat_table(stats)
            if hb_table:
                body.mount(Static(hb_table))
