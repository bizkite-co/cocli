from textual.app import ComposeResult
from textual.widgets import Static, Label
from textual.containers import VerticalScroll, Container, Horizontal
from textual import work
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from typing import Any, Dict, Optional, List, TYPE_CHECKING, cast
import asyncio
from datetime import datetime

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
            self.update_view()

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
            stats_task = asyncio.to_thread(app.services.reporting_service.get_campaign_stats, campaign)
            health_task = app.services.reporting_service.get_cluster_health()
            
            stats, health = await asyncio.gather(stats_task, health_task)
            
            # Re-fetch environment (it's fast)
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
        env_text = Text.assemble(
            ("Campaign: ", "bold cyan"), (f"{self.status_data.get('campaign', 'None')}\n", "green"),
            ("Context:  ", "bold cyan"), (f"{self.status_data.get('context', 'None')}\n", "green"),
            ("Strategy: ", "bold cyan"), (f"{self.status_data.get('strategy', 'Unknown')}\n", "yellow")
        )
        for detail in self.status_data.get("strategy_details", []):
            env_text.append(f"  - {detail}\n", "dim")
        
        body.mount(Static(Panel(env_text, title="Environment Status", border_style="blue")))

        # 2. Cluster Health (SSH)
        if self.cluster_health:
            health_table = Table(title="Cluster Health (SSH Real-time)", expand=True)
            health_table.add_column("Node", style="cyan")
            health_table.add_column("Status", style="bold")
            health_table.add_column("Uptime", style="magenta")
            health_table.add_column("Voltage/Throttle", style="yellow")
            health_table.add_column("Containers", style="green")

            for node in self.cluster_health:
                status = "[green]ONLINE[/green]" if node.get("online") else "[red]OFFLINE[/red]"
                uptime = node.get("uptime", "N/A").split("up")[1].split(",")[0].strip() if "up" in node.get("uptime", "") else "N/A"
                vt = f"{node.get('voltage','N/A')} / {node.get('throttled','N/A')}"
                
                containers = []
                for c in node.get("containers", []):
                    name = c[0].replace("cocli-worker-", "")
                    containers.append(name)
                
                health_table.add_row(
                    node.get("label", node.get("host", "unknown")),
                    status,
                    uptime,
                    vt,
                    ", ".join(containers) if containers else "None"
                )
            body.mount(Static(health_table))

        # 3. Stats Panel
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
