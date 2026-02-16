import typer
import os
from rich.console import Console

from ..core.config import get_context, get_campaign

app = typer.Typer()
console = Console()

@app.command()
def status(
    stats: bool = typer.Option(False, "--stats", "-s", help="Show detailed campaign stats and queue depth.")
) -> None:
    """
    Displays the current status of the cocli environment, including context, campaign, and scrape strategy.
    """
    console.rule("[bold blue]Cocli Environment Status[/bold blue]")

    # Context
    context_filter = get_context()
    if context_filter:
        console.print(f"Current Context: [bold green]{context_filter}[/]")
    else:
        console.print("Current Context: [dim]None[/dim]")

    # Campaign
    campaign_name = get_campaign()
    if campaign_name:
        console.print(f"Current Campaign: [bold green]{campaign_name}[/]")
    else:
        console.print("Current Campaign: [dim]None[/dim]")

    if stats and campaign_name:
        from ..core.reporting import get_campaign_stats
        from datetime import datetime, UTC
        
        with console.status(f"[bold green]Fetching stats for {campaign_name}..."):
            data = get_campaign_stats(campaign_name)
        
        console.print("")
        console.rule(f"[bold blue]Campaign Stats: {campaign_name}[/bold blue]")
        
        # 1. Queues
        q_data = data.get("s3_queues") or data.get("local_queues", {})
        q_source = "S3 (Cloud)" if data.get("s3_queues") else "Local Filesystem"
        
        console.print(f"Queue Source: [yellow]{q_source}[/]")
        from rich.table import Table
        table = Table(title="Queue Depth & Age", header_style="bold magenta")
        table.add_column("Queue")
        table.add_column("Pending", justify="right")
        table.add_column("In-Flight", justify="right")
        table.add_column("Completed", justify="right")
        table.add_column("Last Completion")

        for name, metrics in q_data.items():
            last_ts = metrics.get("last_completed_at")
            age_str = "[dim]N/A[/dim]"
            if last_ts:
                dt = datetime.fromisoformat(last_ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                diff = datetime.now(UTC) - dt
                
                if diff.total_seconds() < 60:
                    age_str = f"[bold green]{int(diff.total_seconds())}s ago[/]"
                elif diff.total_seconds() < 3600:
                    age_str = f"[bold green]{int(diff.total_seconds()/60)}m ago[/]"
                elif diff.total_seconds() < 86400:
                    age_str = f"[yellow]{int(diff.total_seconds()/3600)}h ago[/]"
                else:
                    age_str = f"[red]{int(diff.total_seconds()/86400)}d ago[/]"

            table.add_row(
                name,
                str(metrics.get("pending", 0)),
                str(metrics.get("inflight", 0)),
                str(metrics.get("completed", 0)),
                age_str
            )
        console.print(table)

        # 2. Worker Heartbeats
        heartbeats = data.get("worker_heartbeats", [])
        if heartbeats:
            hb_table = Table(title="Worker Heartbeats (S3)", header_style="bold cyan")
            hb_table.add_column("Hostname")
            hb_table.add_column("Workers (S/D/E)")
            hb_table.add_column("CPU")
            hb_table.add_column("RAM")
            hb_table.add_column("Last Seen")

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
            console.print(hb_table)

    console.print("")

    console.print("")
    console.rule("[bold blue]Scrape Strategy[/bold blue]")

    # Scrape Strategy Detection
    is_fargate = os.getenv("COCLI_RUNNING_IN_FARGATE") == "true"
    aws_profile = os.getenv("AWS_PROFILE")
    local_dev = os.getenv("LOCAL_DEV")
    
    strategy = "Unknown"
    details = []

    if is_fargate:
        strategy = "Cloud / Fargate"
        details.append("Running inside AWS Fargate container")
        details.append("Using IAM Task Role for permissions")
    elif local_dev:
        strategy = "Local Docker (Hybrid)"
        details.append("Running in local Docker container")
        if aws_profile:
             details.append(f"Using AWS Profile: [cyan]{aws_profile}[/cyan]")
    else:
        strategy = "Local Host"
        details.append("Running directly on host machine")
        if aws_profile:
             details.append(f"Using AWS Profile: [cyan]{aws_profile}[/cyan]")
        else:
             details.append("Using default AWS credentials chain")

    console.print(f"Current Strategy: [bold yellow]{strategy}[/bold yellow]")
    for detail in details:
        console.print(f"  - {detail}")

    # Queue Config
    queue_url = os.getenv("COCLI_ENRICHMENT_QUEUE_URL")
    if queue_url:
        console.print(f"Enrichment Queue: [dim]{queue_url}[/dim]")

