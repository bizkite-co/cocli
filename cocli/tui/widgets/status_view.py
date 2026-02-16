from textual.widgets import Static, Label
from textual.containers import VerticalScroll
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from typing import Any, Dict, Optional

class StatusView(VerticalScroll):
    """A widget to display the current cocli environment status."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.status_data: Optional[Dict[str, Any]] = None

    def on_mount(self) -> None:
        self.refresh_status()

    def refresh_status(self) -> None:
        app = self.app
        if hasattr(app, "services"):
            self.status_data = app.services.reporting_service.get_environment_status()
            # Also fetch stats if campaign is set
            if self.status_data and self.status_data.get("campaign"):
                stats = app.services.reporting_service.get_campaign_stats(self.status_data["campaign"])
                self.status_data["stats"] = stats
            
            self.update_view()

    def update_view(self) -> None:
        if not self.status_data:
            self.mount(Label("Failed to load status data."))
            return

        self.remove_children()
        
        # 1. Environment Panel
        env_text = Text.assemble(
            ("Campaign: ", "bold cyan"), (f"{self.status_data.get('campaign', 'None')}\n", "green"),
            ("Context:  ", "bold cyan"), (f"{self.status_data.get('context', 'None')}\n", "green"),
            ("Strategy: ", "bold cyan"), (f"{self.status_data.get('strategy', 'Unknown')}\n", "yellow")
        )
        for detail in self.status_data.get("strategy_details", []):
            env_text.append(f"  - {detail}\n", "dim")
        
        if self.status_data.get("enrichment_queue_url"):
            env_text.append("Queue URL: ", "bold cyan")
            env_text.append(f"{self.status_data['enrichment_queue_url']}\n", "dim")

        self.mount(Static(Panel(env_text, title="Environment Status", border_style="blue")))

        # 2. Stats Panel (if available)
        stats = self.status_data.get("stats")
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
            self.mount(Static(table))

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
                self.mount(Static(hb_table))
