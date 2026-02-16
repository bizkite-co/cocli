from textual.app import ComposeResult
from textual.widgets import Static, Label, Button
from textual.containers import VerticalScroll, Container, Horizontal
from textual import on, work
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from typing import Any, Dict, Optional, TYPE_CHECKING, cast
import asyncio

if TYPE_CHECKING:
    from ..app import CocliApp

class StatusView(VerticalScroll):
    """A widget to display the current cocli environment status with cached data support."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.status_data: Optional[Dict[str, Any]] = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="status_header"):
            yield Label("Environment Status", id="status_title")
            yield Label("", id="status_last_updated")
            yield Button("Refresh", id="btn_refresh_status", variant="primary")
            yield Static("", id="status_refresh_indicator")
        
        yield Container(id="status_body")

    def on_mount(self) -> None:
        self.load_initial_data()

    def load_initial_data(self) -> None:
        app = cast("CocliApp", self.app)
        if not hasattr(app, "services"):
            return

        campaign = app.services.reporting_service.campaign_name
        # 1. Load context status (always fast)
        self.status_data = app.services.reporting_service.get_environment_status()
        
        # 2. Try to load cached stats
        cached_stats = app.services.reporting_service.load_cached_report(campaign, "status")
        if cached_stats:
            self.status_data["stats"] = cached_stats
            self.update_view()
        else:
            # If no cache, trigger a refresh
            self.action_refresh()

    @on(Button.Pressed, "#btn_refresh_status")
    def action_refresh(self) -> None:
        self.trigger_refresh()

    @work(exclusive=True, thread=True)
    async def trigger_refresh(self) -> None:
        app = cast("CocliApp", self.app)
        indicator = self.query_one("#status_refresh_indicator", Static)
        indicator.update("[bold yellow] Refreshing...[/bold yellow]")
        
        try:
            campaign = app.services.reporting_service.campaign_name
            # This is the slow blocking call, now in a thread
            stats = await asyncio.to_thread(app.services.reporting_service.get_campaign_stats, campaign)
            
            # Re-fetch environment (it's fast)
            env = await asyncio.to_thread(app.services.reporting_service.get_environment_status)
            env["stats"] = stats
            
            self.status_data = env
            self.call_after_refresh(self.update_view)
            indicator.update("[bold green] Done[/bold green]")
            await asyncio.sleep(2)
            indicator.update("")
        except Exception as e:
            indicator.update(f"[bold red] Error: {e}[/bold red]")

    def update_view(self) -> None:
        if not self.status_data:
            return

        body = self.query_one("#status_body", Container)
        body.remove_children()
        
        # Update Timestamp in Header
        stats = self.status_data.get("stats", {})
        last_upd = stats.get("last_updated", "Never")
        if last_upd != "Never":
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(last_upd)
                last_upd = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
        self.query_one("#status_last_updated", Label).update(f"Generated: {last_upd}")

        # 1. Environment Panel
        env_text = Text.assemble(
            ("Campaign: ", "bold cyan"), (f"{self.status_data.get('campaign', 'None')}\n", "green"),
            ("Context:  ", "bold cyan"), (f"{self.status_data.get('context', 'None')}\n", "green"),
            ("Strategy: ", "bold cyan"), (f"{self.status_data.get('strategy', 'Unknown')}\n", "yellow")
        )
        for detail in self.status_data.get("strategy_details", []):
            env_text.append(f"  - {detail}\n", "dim")
        
        body.mount(Static(Panel(env_text, title="Environment Status", border_style="blue")))

        # 2. Stats Panel
        if stats and not stats.get("error"):
            from datetime import datetime, UTC
            
            # Queues Table
            q_data = stats.get("s3_queues") or stats.get("local_queues", {})
            q_source = "S3 (Cloud)" if stats.get("s3_queues") else "Local Filesystem"
            
            table = Table(title=f"Queue Depth & Age (Source: {q_source})", expand=True)
            table.add_column("Queue", style="cyan")
            table.add_column("Pending", justify="right", style="magenta")
            table.add_column("In-Flight", justify="right", style="blue")
            table.add_column("Completed", justify="right", style="green")
            table.add_column("Last Completion", style="yellow")

            for name, metrics in q_data.items():
                last_ts = metrics.get("last_completed_at")
                age_str = "N/A"
                if last_ts:
                    try:
                        dt = datetime.fromisoformat(last_ts)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=UTC)
                        diff = datetime.now(UTC) - dt
                        if diff.total_seconds() < 60:
                            age_str = f"{int(diff.total_seconds())}s ago"
                        elif diff.total_seconds() < 3600:
                            age_str = f"{int(diff.total_seconds()/60)}m ago"
                        elif diff.total_seconds() < 86400:
                            age_str = f"{int(diff.total_seconds()/3600)}h ago"
                        else:
                            age_str = f"{int(diff.total_seconds()/86400)}d ago"
                    except Exception:
                        age_str = last_ts

                table.add_row(
                    name, 
                    str(metrics.get("pending", 0)), 
                    str(metrics.get("inflight", 0)), 
                    str(metrics.get("completed", 0)), 
                    age_str
                )
            body.mount(Static(table))

            # Worker Heartbeats
            heartbeats = stats.get("worker_heartbeats", [])
            if heartbeats:
                hb_table = Table(title="Worker Heartbeats (S3)", expand=True)
                hb_table.add_column("Hostname", style="cyan")
                hb_table.add_column("Workers (S/D/E)", style="magenta")
                hb_table.add_column("CPU", style="blue")
                hb_table.add_column("RAM", style="green")
                hb_table.add_column("Last Seen", style="yellow")

                for hb in heartbeats:
                    ls_str = hb.get("last_seen", "unknown")
                    try:
                        ls_dt = datetime.fromisoformat(ls_str)
                        ls_diff = datetime.now(UTC) - ls_dt
                        ls_age = f"{int(ls_diff.total_seconds())}s ago"
                    except Exception:
                        ls_age = ls_str
                    workers = hb.get("workers", {})
                    w_str = f"{workers.get('scrape',0)}/{workers.get('details',0)}/{workers.get('enrichment',0)}"
                    hb_table.add_row(
                        hb.get("hostname", "unknown"), 
                        w_str, 
                        f"{hb.get('system',{}).get('cpu_percent',0)}%", 
                        f"{hb.get('system',{}).get('memory_available_gb',0)}GB free", 
                        ls_age
                    )
                body.mount(Static(hb_table))
