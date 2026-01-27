import typer
import json
from rich.console import Console
from rich.progress import track
from typing import Optional

from cocli.core.config import get_campaign
from cocli.core.queue.factory import get_queue_manager
from cocli.models.queue import QueueMessage
from cocli.models.company import Company

app = typer.Typer()
console = Console()

@app.command()
def main(
    campaign_name: Optional[str] = typer.Argument(None, help="Campaign name. Defaults to current context."),
    limit: int = typer.Option(100, "--limit", "-l", help="Number of prospects to re-scrape."),
    tag: str = typer.Option("batch-v6-test-1", "--tag", "-t", help="Tag to apply to selected prospects."),
) -> None:
    """
    Selects N prospects with missing emails, tags them, and enqueues them for re-scraping.
    """
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified and no active context.[/bold red]")
        raise typer.Exit(1)

    console.print(f"[bold]Batch Re-scrape Test for campaign: {campaign_name}[/bold]")
    
    # 1. Load all companies and filter
    all_companies = Company.get_all()
    target_prospects = []
    
    for company in track(all_companies, description="Filtering prospects..."):
        # Check if part of the campaign
        if campaign_name not in company.tags:
            continue
            
        # Check if email is missing
        if company.email:
            continue
            
        # Must have a domain to scrape
        if not company.domain:
            continue
            
        target_prospects.append(company)
        if len(target_prospects) >= limit:
            break

    if not target_prospects:
        console.print("[yellow]No eligible prospects found.[/yellow]")
        return

    console.print(f"Selected [bold green]{len(target_prospects)}[/bold green] prospects for re-scraping.")

    # 2. Tag and Save
    selection_data = []
    queue_manager = get_queue_manager("enrichment", use_cloud=True, campaign_name=campaign_name)
    
    for company in track(target_prospects, description="Tagging and Enqueuing..."):
        # Add tracking tag
        if tag not in company.tags:
            company.tags.append(tag)
            company.save() # Persist tag to tags.lst
            
        if not company.domain:
            continue

        # Save selection info for reference
        selection_data.append({
            "name": company.name,
            "slug": company.slug,
            "domain": company.domain
        })
        
        # 3. Enqueue with force_refresh
        msg = QueueMessage(
            domain=company.domain,
            company_slug=company.slug,
            campaign_name=campaign_name,
            force_refresh=True, # Ensure new scraper version is triggered
            ttl_days=30,
            ack_token=None,
        )
        queue_manager.push(msg)

    # 4. Save reference file
    from cocli.core.config import get_temp_dir
    output_path = get_temp_dir() / "batch_test_selection.json"
    output_path.write_text(json.dumps(selection_data, indent=2))
    
    console.print("\n[bold green]Success![/bold green]")
    console.print(f"Tagged and enqueued {len(target_prospects)} prospects.")
    console.print(f"Selection reference saved to: [bold]{output_path}[/bold]")
    console.print("Monitoring Fargate logs for processing...")

if __name__ == "__main__":
    app()
