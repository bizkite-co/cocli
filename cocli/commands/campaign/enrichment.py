import typer
import logging
from typing import Optional
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn

from ...core.config import get_campaign
from ...core.queue.factory import get_queue_manager
from ...models.companies.company import Company
from ...models.campaigns.queues.base import QueueMessage

logger = logging.getLogger(__name__)
console = Console()
app = typer.Typer(no_args_is_help=True)

@app.command(name="queue-enrichment")
def queue_enrichment(
    campaign_name: Optional[str] = typer.Argument(None),
    force: bool = typer.Option(False, "--force", "-f", help="Force re-enrichment even if fresh data exists."),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Limit the number of companies to enqueue."),
    has_email: bool = typer.Option(True, "--has-email", help="Only enqueue companies that already have an email address."),
) -> None:
    """
    Enqueues companies from the campaign for website enrichment into the DFQ.
    """
    effective_campaign = campaign_name or get_campaign()
    
    if not effective_campaign:
        console.print("[red]No campaign specified and no active context.[/red]")
        raise typer.Exit(1)

    console.print(f"[bold blue]Queuing enrichment tasks for campaign: {effective_campaign}[/bold blue]")
    
    # Force DFQ for this operation as requested
    import os
    os.environ["COCLI_QUEUE_TYPE"] = "filesystem"
    
    queue_manager = get_queue_manager("enrichment", use_cloud=True, queue_type="enrichment", campaign_name=effective_campaign)
    
    # Iterate through all companies
    # Note: We might want to filter by campaign tags if we have thousands of global companies
    # For now, we'll iterate and check for campaign tag.
    
    companies_to_queue = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task_id = progress.add_task("[cyan]Scanning companies...[/cyan]", total=None)
        
        for company in Company.get_all():
            if effective_campaign not in company.tags:
                continue
                
            if has_email and not company.email and not company.all_emails:
                continue
            
            companies_to_queue.append(company)
            progress.advance(task_id)
            
            if limit and len(companies_to_queue) >= limit:
                break

    if not companies_to_queue:
        console.print("[yellow]No companies found matching criteria.[/yellow]")
        return

    console.print(f"[green]Found {len(companies_to_queue)} companies to enqueue.[/green]")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        task_id = progress.add_task(f"[cyan]Pushing {len(companies_to_queue)} tasks to DFQ...[/cyan]", total=len(companies_to_queue))
        
        for company in companies_to_queue:
            # Trim query parameters for a cleaner starting URL
            clean_domain = company.domain
            if clean_domain and "?" in clean_domain:
                clean_domain = clean_domain.split("?")[0]

            msg = QueueMessage(
                domain=clean_domain or "unknown",
                company_slug=company.slug,
                campaign_name=effective_campaign,
                force_refresh=force,
                ttl_days=30,
                ack_token=None
            )
            queue_manager.push(msg)
            progress.advance(task_id)

    console.print(f"[bold green]Successfully queued {len(companies_to_queue)} enrichment tasks.[/bold green]")
