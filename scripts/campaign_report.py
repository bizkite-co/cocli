import typer
import json
from datetime import datetime
from typing import Optional
from rich.console import Console
from rich.table import Table
from cocli.core.config import get_campaign, load_campaign_config
from cocli.core.reporting import get_campaign_stats, get_boto3_session

app = typer.Typer()
console = Console()

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

    if not as_json:
        console.print(f"Generating report for campaign: [bold cyan]{campaign_name}[/bold cyan]...")
    
    stats = get_campaign_stats(campaign_name)
    stats['last_updated'] = datetime.now().isoformat()
    stats['campaign_name'] = campaign_name

    if as_json:
        print(json.dumps(stats, indent=2))
    else:
        # Display Table
        table = Table(title=f"Campaign Report: {campaign_name}")
        table.add_column("Stage", style="cyan")
        table.add_column("Count", justify="right", style="magenta")
        table.add_column("Percentage/Details", justify="right", style="green")

        using_cloud_queue = stats.get('using_cloud_queue', False)

        # 1. Pipeline Status (Workers & Queues)
        if using_cloud_queue:
            # Worker Status
            active_fargate = stats.get('active_fargate_tasks', 0)
            table.add_row("Active Enrichment Workers (Fargate)", str(active_fargate), "[bold green]Running[/bold green]" if active_fargate > 0 else "[dim]Stopped[/dim]")

            # Queues & Processing
            # Scrape Tasks (gm-list)
            scrape_pending = stats.get('scrape_tasks_pending', 0)
            scrape_inflight = stats.get('scrape_tasks_inflight', 0)
            table.add_row("Scrape Tasks (gm-list)", f"{scrape_pending} / [blue]{scrape_inflight} Active[/blue]", "[yellow]SQS[/yellow]")

            # GM List Items (gm-details)
            gm_pending = stats.get('gm_list_item_pending', 0)
            gm_inflight = stats.get('gm_list_item_inflight', 0)
            table.add_row("GM List Items (gm-details)", f"{gm_pending} / [blue]{gm_inflight} Active[/blue]", "[yellow]SQS[/yellow]")

            # Enrichment
            enrich_pending = stats.get('enrichment_pending', 0)
            enrich_inflight = stats.get('enrichment_inflight', 0)
            table.add_row("Enrichment Queue (SQS)", f"{enrich_pending} / [blue]{enrich_inflight} Active[/blue]", "[yellow]SQS[/yellow]")

            # Local Enrichment (RPI Cluster)
            local_pending = stats.get('local_enrichment_pending', 0)
            local_inflight = stats.get('local_enrichment_inflight', 0)
            if local_pending > 0 or local_inflight > 0:
                table.add_row("Enrichment Queue (Local)", f"{local_pending} / [blue]{local_inflight} Active[/blue]", "[cyan]Filesystem[/cyan]")
        else:
            # Local Queues
            table.add_row("Queue Pending", str(stats.get('enrichment_pending', 0)), "[yellow]Waiting[/yellow]")
            table.add_row("Queue Processing", str(stats.get('enrichment_inflight', 0)), "[blue]In Flight[/blue]")

        # 2. Local Queue Status
        table.add_row("Queue Failed (Local)", str(stats.get('failed_count', 0)), "[red]Errors/Retries[/red]")
        table.add_row("Queue Completed (Local)", str(stats.get('completed_count', 0)), "[dim]Done[/dim]") 

        # 3. Data Funnel
        total_prospects = stats.get('prospects_count', 0)
        table.add_row("Prospects (gm-detail)", str(total_prospects), "100%")

        # Enriched %
        enriched_count = stats.get('enriched_count', 0)
        deep_enriched_count = stats.get('deep_enriched_count', 0)
        total_enriched_global = stats.get('total_enriched_global', 0)
        enriched_pct = f"{(enriched_count / total_prospects * 100):.1f}%" if total_prospects else "0%"
        deep_pct = f"{(deep_enriched_count / enriched_count * 100):.1f}%" if enriched_count else "0%"
        
        table.add_row("Enriched (Campaign)", str(enriched_count), enriched_pct)
        table.add_row("Deep Enriched (Sitemap/Nav)", str(deep_enriched_count), f"{deep_pct} (of Enriched)")
        table.add_row("Enriched (Global Pool)", str(total_enriched_global), "[dim]Historical[/dim]")
        
        # Email %
        companies_with_emails = stats.get('companies_with_emails_count', 0)
        total_emails = stats.get('emails_found_count', 0)
        email_pct = f"{(companies_with_emails / enriched_count * 100):.1f}%" if enriched_count else "0%"
        
        table.add_row("Companies w/ Emails", str(companies_with_emails), f"{email_pct} (Yield)")
        table.add_row("Total Emails Found", str(total_emails), "[bold green]Index[/bold green]")

        # 4. Anomaly Monitor
        anomaly_stats = stats.get('anomaly_stats', {})
        if anomaly_stats:
            risk = anomaly_stats.get('shadow_ban_risk', 'LOW')
            risk_style = "bold red" if risk == "HIGH" else "green"
            empty_pct = (anomaly_stats['empty_scrapes'] / anomaly_stats['total_scrapes'] * 100) if anomaly_stats['total_scrapes'] else 0
            table.add_row("Shadow Ban Risk", risk, style=risk_style)
            table.add_row("Empty Scrape Rate", f"{empty_pct:.1f}%", "[dim]Anomaly Indicator[/dim]")

        console.print(table)

        # Worker Source Breakdown
        worker_stats = stats.get('worker_stats', {})
        if worker_stats:
            worker_table = Table(title="Processing Sources (Details)")
            worker_table.add_column("Worker Type", style="cyan")
            worker_table.add_column("Count", justify="right", style="magenta")
            worker_table.add_column("Share", justify="right", style="green")
            
            total = sum(worker_stats.values())
            for worker, count in sorted(worker_stats.items(), key=lambda x: x[1], reverse=True):
                share = f"{(count / total * 100):.1f}%" if total else "0%"
                worker_table.add_row(worker, str(count), share)
            console.print(worker_table)
        
        failed_count = stats.get('failed_count', 0)
        if failed_count > 0:
            console.print(f"\n[bold red]Warning:[/bold red] {failed_count} tasks failed locally. Check logs or move them back to pending to retry.")
        
        if using_cloud_queue:
            pending = stats.get('enrichment_pending', 0)
            console.print(f"[dim]Note: Report shows local data. SQS has {pending} pending items.[/dim]")

    if upload:
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
