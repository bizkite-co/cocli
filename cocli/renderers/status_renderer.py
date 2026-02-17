from typing import Any, Dict, List, Optional
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from datetime import datetime, UTC

def render_environment_panel(status_data: Dict[str, Any]) -> Panel:
    """Renders the standard environment status panel."""
    env_text = Text.assemble(
        ("Campaign: ", "bold cyan"), (f"{status_data.get('campaign', 'None')}\n", "green"),
        ("Context:  ", "bold cyan"), (f"{status_data.get('context', 'None')}\n", "green"),
        ("Strategy: ", "bold cyan"), (f"{status_data.get('strategy', 'Unknown')}\n", "yellow")
    )
    for detail in status_data.get("strategy_details", []):
        env_text.append(f"  - {detail}\n", "dim")
    
    return Panel(env_text, title="Environment Status", border_style="blue")

def render_queue_table(stats: Dict[str, Any]) -> Table:
    """Renders the queue depth and age table."""
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
    return table

def render_cluster_health_table(health_data: List[Dict[str, Any]]) -> Table:
    """Renders the real-time SSH cluster health table."""
    table = Table(title="Cluster Health (SSH Real-time)", expand=True)
    table.add_column("Node", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Uptime", style="magenta")
    table.add_column("Voltage/Throttle", style="yellow")
    table.add_column("Containers", style="green")

    for node in health_data:
        status = "[green]ONLINE[/green]" if node.get("online") else "[red]OFFLINE[/red]"
        uptime = node.get("uptime", "N/A").split("up")[1].split(",")[0].strip() if "up" in node.get("uptime", "") else "N/A"
        vt = f"{node.get('voltage','N/A')} / {node.get('throttled','N/A')}"
        
        containers = []
        for c in node.get("containers", []):
            # c is [Name, Status]
            name = c[0].replace("cocli-worker-", "")
            containers.append(name)
        
        table.add_row(
            node.get("label", node.get("host", "unknown")),
            status,
            uptime,
            vt,
            ", ".join(containers) if containers else "None"
        )
    return table

def render_worker_heartbeat_table(stats: Dict[str, Any]) -> Optional[Table]:
    """Renders the worker heartbeats table from S3 stats."""
    heartbeats = stats.get("worker_heartbeats", [])
    if not heartbeats:
        return None
        
    table = Table(title="Worker Heartbeats (S3)", expand=True)
    table.add_column("Hostname", style="cyan")
    table.add_column("Workers (S/D/E)", style="magenta")
    table.add_column("CPU", style="blue")
    table.add_column("RAM", style="green")
    table.add_column("Last Seen", style="yellow")

    for hb in heartbeats:
        ls_str = hb.get("last_seen", "unknown")
        try:
            ls_dt = datetime.fromisoformat(ls_str)
            if ls_dt.tzinfo is None:
                ls_dt = ls_dt.replace(tzinfo=UTC)
            ls_diff = datetime.now(UTC) - ls_dt
            ls_age = f"{int(ls_diff.total_seconds())}s ago"
        except Exception:
            ls_age = ls_str
        workers = hb.get("workers", {})
        w_str = f"{workers.get('scrape',0)}/{workers.get('details',0)}/{workers.get('enrichment',0)}"
        table.add_row(
            hb.get("hostname", "unknown"), 
            w_str, 
            f"{hb.get('system',{}).get('cpu_percent',0)}%", 
            f"{hb.get('system',{}).get('memory_available_gb',0)}GB free", 
            ls_age
        )
    return table
