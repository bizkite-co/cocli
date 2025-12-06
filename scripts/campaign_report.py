import typer
import csv
import os
import boto3 # type: ignore
from typing import Optional
from rich.console import Console
from rich.table import Table
from cocli.core.config import get_scraped_data_dir, get_companies_dir, get_cocli_base_dir, get_campaign

app = typer.Typer()
console = Console()

def get_sqs_pending_count(queue_url: str) -> int:
    try:
        sqs = boto3.client("sqs")
        response = sqs.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=['ApproximateNumberOfMessages']
        )
        return int(response['Attributes']['ApproximateNumberOfMessages'])
    except Exception as e:
        console.print(f"[yellow]Warning: Could not fetch SQS count: {e}[/yellow]")
        return 0

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

    # 1. Total Prospects (gm-detail)
    prospects_csv = get_scraped_data_dir() / campaign_name / "prospects" / "prospects.csv"
    total_prospects = 0
    if prospects_csv.exists():
        with open(prospects_csv, 'r', encoding='utf-8', errors='ignore') as f:
            total_prospects = sum(1 for _ in f) - 1 # Subtract header
            if total_prospects < 0: 
                total_prospects = 0

    # 2. Queue Stats
    queue_url = os.getenv("COCLI_SQS_QUEUE_URL")
    using_cloud_queue = queue_url is not None
    
    if using_cloud_queue and queue_url:
        pending_count = get_sqs_pending_count(queue_url)
        processing_count = 0 # Harder to track in flight without tracking logic
        # We could check messages not visible?
        # For now, assume SQS ApproximateNumberOfMessagesNotVisible = Processing
        try:
            sqs = boto3.client("sqs")
            response = sqs.get_queue_attributes(
                QueueUrl=queue_url,
                AttributeNames=['ApproximateNumberOfMessagesNotVisible']
            )
            processing_count = int(response['Attributes']['ApproximateNumberOfMessagesNotVisible'])
        except Exception:
            pass
    else:
        queue_base = get_cocli_base_dir() / "queues" / f"{campaign_name}_enrichment"
        pending_count = sum(1 for _ in (queue_base / "pending").iterdir() if _.is_file()) if (queue_base / "pending").exists() else 0
        processing_count = sum(1 for _ in (queue_base / "processing").iterdir() if _.is_file()) if (queue_base / "processing").exists() else 0
    
    # Failed/Completed are still local concepts unless we use DLQ/S3
    queue_base = get_cocli_base_dir() / "queues" / f"{campaign_name}_enrichment"
    failed_count = sum(1 for _ in (queue_base / "failed").iterdir() if _.is_file()) if (queue_base / "failed").exists() else 0
    completed_count = sum(1 for _ in (queue_base / "completed").iterdir() if _.is_file()) if (queue_base / "completed").exists() else 0

    # 3. Enriched & Emails (Scan companies)
    enriched_count = 0
    emails_found_count = 0
    
    slugs = set()
    if prospects_csv.exists():
        with open(prospects_csv, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            from cocli.core.utils import slugify
            for row in reader:
                if row.get('Domain'):
                    slugs.add(slugify(row['Domain']))
    
    companies_dir = get_companies_dir()
    for slug in slugs:
        company_path = companies_dir / slug
        if (company_path / "enrichments" / "website.md").exists():
            enriched_count += 1
            
            # Check for email in the compiled index or website enrichment
            # Let's check _index.md for "email: " string to avoid full yaml parse
            index_path = company_path / "_index.md"
            if index_path.exists():
                try:
                    content = index_path.read_text()
                    if "email: " in content and "email: null" not in content and "email: ''" not in content:
                        emails_found_count += 1
                except Exception:
                    pass

    # Display Table
    table = Table(title=f"Campaign Report: {campaign_name}")
    table.add_column("Stage", style="cyan")
    table.add_column("Count", justify="right", style="magenta")
    table.add_column("Percentage/Details", justify="right", style="green")

    table.add_row("Prospects (gm-detail)", str(total_prospects), "100%")
    
    # Queue Breakdown
    if using_cloud_queue:
        table.add_row("Queue Pending (Cloud)", str(pending_count), "[yellow]SQS Available[/yellow]")
        table.add_row("Queue In-Flight (Cloud)", str(processing_count), "[blue]SQS Invisible[/blue]")
    else:
        table.add_row("Queue Pending", str(pending_count), "[yellow]Waiting[/yellow]")
        table.add_row("Queue Processing", str(processing_count), "[blue]In Flight[/blue]")
        
    table.add_row("Queue Failed (Local)", str(failed_count), "[red]Errors/Retries[/red]")
    table.add_row("Queue Completed (Local)", str(completed_count), "[dim]Done[/dim]") 

    # Enriched % relative to total
    enriched_pct = f"{(enriched_count / total_prospects * 100):.1f}%" if total_prospects else "0%"
    table.add_row("Enriched (Local)", str(enriched_count), enriched_pct)
    
    # Email % relative to Enriched (Yield)
    email_pct = f"{(emails_found_count / enriched_count * 100):.1f}%" if enriched_count else "0%"
    table.add_row("Emails Found (Local)", str(emails_found_count), f"{email_pct} (Yield)")

    console.print(table)
    
    if failed_count > 0:
        console.print(f"\n[bold red]Warning:[/bold red] {failed_count} tasks failed locally. Check logs or move them back to pending to retry.")
    
    if using_cloud_queue:
        console.print(f"[dim]Note: Report shows local data. SQS has {pending_count} pending items. Run consumer to process.[/dim]")

if __name__ == "__main__":
    app()
