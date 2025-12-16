import typer
from typing import Optional
from rich.console import Console
from rich.table import Table
from cocli.core.config import get_campaign
from cocli.core.reporting import get_campaign_stats

app = typer.Typer()
console = Console()

@app.command()
def main(campaign_name: Optional[str] = typer.Argument(None, help="Campaign name. Defaults to current context.")) -> None:
    """
    Generates a data funnel report for the specified campaign.
    """
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified and no current context set.[/bold red]")
        raise typer.Exit(1)

    console.print(f"Generating report for campaign: [bold cyan]{campaign_name}[/bold cyan]...")
    stats = get_campaign_stats(campaign_name)

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
        table.add_row("Enrichment Queue", f"{enrich_pending} / [blue]{enrich_inflight} Active[/blue]", "[yellow]SQS[/yellow]")
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
    enriched_pct = f"{(enriched_count / total_prospects * 100):.1f}%" if total_prospects else "0%"
    table.add_row("Enriched (Local)", str(enriched_count), enriched_pct)
    
    # Email %
    emails_found_count = stats.get('emails_found_count', 0)
    email_pct = f"{(emails_found_count / enriched_count * 100):.1f}%" if enriched_count else "0%"
    table.add_row("Emails Found (Local)", str(emails_found_count), f"{email_pct} (Yield)")

    console.print(table)
    
    failed_count = stats.get('failed_count', 0)
    if failed_count > 0:
        console.print(f"\n[bold red]Warning:[/bold red] {failed_count} tasks failed locally. Check logs or move them back to pending to retry.")
    
    if using_cloud_queue:
        pending = stats.get('enrichment_pending', 0)
        console.print(f"[dim]Note: Report shows local data. SQS has {pending} pending items.[/dim]")

if __name__ == "__main__":
    app()