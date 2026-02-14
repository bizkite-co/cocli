import typer
import json
from datetime import datetime, timezone
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from cocli.core.config import get_campaign, load_campaign_config
from cocli.core.reporting import get_campaign_stats, get_boto3_session

app = typer.Typer()
console = Console()

def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    else:
        return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"

@app.command()
def main(
    campaign_name: Optional[str] = typer.Argument(None, help="Campaign name. Defaults to current context."),
    as_json: bool = typer.Option(False, "--json", help="Output report as JSON."),
    upload: bool = typer.Option(False, "--upload", help="Upload report.json to S3 dashboard bucket.")
) -> None:
    """
    Generates a data funnel report for the specified campaign.
    """
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified and no current context set.[/bold red]")
        raise typer.Exit(1)

    stats = get_campaign_stats(campaign_name)
    stats['last_updated'] = datetime.now(timezone.utc).isoformat()
    stats['campaign_name'] = campaign_name

    if as_json:
        print(json.dumps(stats, indent=2))
        return

    # 1. Campaign Funnel Table
    funnel_table = Table(title=f"Campaign Funnel: {campaign_name}", box=None)
    funnel_table.add_column("Stage", style="cyan")
    funnel_table.add_column("Count", justify="right", style="magenta")
    funnel_table.add_column("Yield", justify="right", style="green")

    prospects = stats.get('prospects_count', 0)
    enriched = stats.get('enriched_count', 0)
    w_emails = stats.get('companies_with_emails_count', 0)
    total_emails = stats.get('emails_found_count', 0)
    deep = stats.get('deep_enriched_count', 0)

    enriched_pct = f"{(enriched/prospects*100):.1f}%" if prospects else "0%"
    email_yield = f"{(w_emails/enriched*100):.1f}%" if enriched else "0%"
    deep_yield = f"{(deep/enriched*100):.1f}%" if enriched else "0%"

    funnel_table.add_row("Scraped Prospects", str(prospects), "100%")
    funnel_table.add_row("Enriched Companies", str(enriched), enriched_pct)
    funnel_table.add_row("Deep Enrichment", str(deep), deep_yield)
    funnel_table.add_row("Companies w/ Emails", str(w_emails), email_yield)
    funnel_table.add_row("Total Global Pool", str(stats.get('total_enriched_global', 0)), "[dim]Index[/dim]")

    # 2. Queue Status Table
    queue_table = Table(title="Queue Management", box=None)
    queue_table.add_column("Queue Name", style="cyan")
    queue_table.add_column("Provider", style="yellow")
    queue_table.add_column("Pending", justify="right", style="magenta")
    queue_table.add_column("In-Flight", justify="right", style="blue")
    queue_table.add_column("Completed", justify="right", style="green")

    # S3 Queues (Filesystem V2 Remote State)
    s3_queues = stats.get('s3_queues', {})
    for q_name, q_stats in s3_queues.items():
        pending = q_stats.get('pending', 0)
        inflight = q_stats.get('inflight', 0)
        completed = q_stats.get('completed', 0)
        if pending > 0 or inflight > 0 or completed > 0:
            queue_table.add_row(f"{q_name} (Global)", "S3", str(pending), str(inflight), str(completed))

    # Local Queues
    local_queues = stats.get('local_queues', {})
    for q_name, q_stats in local_queues.items():
        pending = q_stats.get('pending', 0)
        inflight = q_stats.get('inflight', 0)
        if pending > 0 or inflight > 0:
            queue_table.add_row(q_name, "Local", str(pending), str(inflight), "-")

    # 3. Cluster Health Table
    cluster_table = Table(title="Cluster Health & Heartbeats", box=None)
    cluster_table.add_column("Host", style="cyan")
    cluster_table.add_column("Status", style="green")
    cluster_table.add_column("Version", style="white")
    cluster_table.add_column("Last Seen", style="yellow")
    cluster_table.add_column("Load/Mem", style="magenta")
    cluster_table.add_column("Active Workers", style="blue")

    # 3.1 Work Distribution (DuckDB Analytics)
    dist_table = Table(title="Cluster Work Distribution (Actual Results)", box=None)
    dist_table.add_column("Host", style="cyan")
    dist_table.add_column("Scrapes", justify="right", style="green")
    dist_table.add_column("Detailed Leads", justify="right", style="magenta")
    dist_table.add_column("Enrichments", justify="right", style="blue")
    dist_table.add_column("Share", justify="right", style="white")

    capacity = stats.get('cluster_capacity', {})
    by_machine_scr = capacity.get('by_machine_scraped', {})
    by_machine_det = capacity.get('by_machine_detailed', {})
    by_machine_enr = capacity.get('by_machine_enriched', {})
    total_scraped = capacity.get('total_scraped', 0)
    total_detailed = capacity.get('total_detailed', 0)
    total_enriched = capacity.get('total_enriched_sampled', 0)

    # Combine machine sets
    all_machines = set(by_machine_scr.keys()) | set(by_machine_det.keys()) | set(by_machine_enr.keys())
    total_work = total_scraped + total_detailed + total_enriched

    for machine in sorted(all_machines):
        count_scr = by_machine_scr.get(machine, 0)
        count_det = by_machine_det.get(machine, 0)
        count_enr = by_machine_enr.get(machine, 0)
        share = f"{((count_scr + count_det + count_enr) / total_work * 100):.1f}%" if total_work > 0 else "0%"
        dist_table.add_row(machine, str(count_scr), str(count_det), str(count_enr), share)

    heartbeats = stats.get('worker_heartbeats', [])
    now = datetime.now(timezone.utc)

    if not heartbeats:
        cluster_table.add_row("[dim]No heartbeats recorded[/dim]", "-", "-", "-", "-", "-")
    else:
        for hb in sorted(heartbeats, key=lambda x: x.get('last_seen', ''), reverse=True):
            last_seen_dt = datetime.fromisoformat(hb['last_seen'].replace("Z", "+00:00"))
            if last_seen_dt.tzinfo is None:
                last_seen_dt = last_seen_dt.replace(tzinfo=timezone.utc)
            
            staleness = (now - last_seen_dt).total_seconds()
            
            status = "[bold green]Online[/bold green]"
            if staleness > 300: # 5 minutes
                status = "[bold red]Stale[/bold red]"
            if staleness > 3600: # 1 hour
                status = "[dim red]Offline[/dim red]"

            sys = hb.get('system', {})
            load = f"{sys.get('cpu_percent', 0)}% / {sys.get('memory_percent', 0)}%"
            
            workers = hb.get('workers', {})
            worker_str = f"S:{workers.get('scrape', 0)} D:{workers.get('details', 0)} E:{workers.get('enrichment', 0)}"

            cluster_table.add_row(
                hb.get('hostname', 'unknown'),
                status,
                hb.get('version', '[dim]unknown[/dim]'),
                format_duration(staleness) + " ago",
                load,
                worker_str
            )

    # 4. Anomaly & Quality
    anomaly_table = Table(title="Quality Metrics", box=None)
    anomaly_table.add_column("Metric", style="cyan")
    anomaly_table.add_column("Value", style="magenta")
    anomaly_table.add_column("Risk", style="green")

    anomaly_stats = stats.get('anomaly_stats', {})
    risk = anomaly_stats.get('shadow_ban_risk', 'LOW')
    risk_style = "bold red" if risk == "HIGH" else "green"
    empty_pct = (anomaly_stats['empty_scrapes'] / anomaly_stats['total_scrapes'] * 100) if anomaly_stats.get('total_scrapes') else 0
    
    anomaly_table.add_row("Shadow Ban Risk", risk, f"[{risk_style}]{risk}[/{risk_style}]")
    anomaly_table.add_row("Empty Scrape Rate", f"{empty_pct:.1f}%", "[dim]Warning > 30%[/dim]")
    anomaly_table.add_row("Total Emails", str(total_emails), "[bold green]Healthy[/bold green]")

    # Print All
    console.print(Panel(f"Campaign: [bold cyan]{campaign_name}[/bold cyan] | Updated: {stats['last_updated']}"))
    console.print(funnel_table)
    console.print(queue_table)
    console.print(cluster_table)
    console.print(dist_table)
    console.print(anomaly_table)

    if upload:
        # Save local copy for debugging/inspection in temp dir
        from cocli.core.config import get_temp_dir
        report_path = get_temp_dir() / f"{campaign_name}.json"
        with open(report_path, "w") as f:
            json.dump(stats, f, indent=2)
        console.print(f"[dim]Saved local report to {report_path}[/dim]")

        config = load_campaign_config(campaign_name)
        s3_config = config.get("aws", {})
        bucket_name = s3_config.get("cocli_web_bucket_name") or "cocli-web-assets-turboheat-net"
        s3_key = f"reports/{campaign_name}.json"
        
        try:
            session = get_boto3_session(config)
            s3 = session.client("s3")
            console.print(f"Uploading report to s3://{bucket_name}/{s3_key}...")
            s3.put_object(
                Bucket=bucket_name,
                Key=s3_key,
                Body=json.dumps(stats, indent=2),
                ContentType="application/json"
            )
            console.print("[bold green]Successfully uploaded report to S3.[/bold green]")
        except Exception as e:
            console.print(f"[bold red]Failed to upload report to S3: {e}[/bold red]")

if __name__ == "__main__":
    app()