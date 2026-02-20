import typer
import csv
import logging
from pathlib import Path
from typing import Optional
from rich.console import Console

from cocli.core.config import get_campaign_scraped_data_dir, get_campaign
from cocli.core.importing import import_prospect
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.models.companies.company import Company
from cocli.core.queue.factory import get_queue_manager
from cocli.models.campaigns.queues.base import QueueMessage

logger = logging.getLogger(__name__)
console = Console()
app = typer.Typer()

@app.command()
def main(
    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign. Defaults to current context."),
    csv_path: Optional[Path] = typer.Option(None, "--csv", "-c", help="Path to the legacy prospects CSV file. Defaults to standard scraped_data location."),
    force: bool = typer.Option(False, "--force", "-f", help="Force re-enrichment even if data exists."),
) -> None:
    """
    Ingests legacy prospects.csv data into the new system.
    1. Creates local company records.
    2. Pushes enrichment tasks to the queue.
    """
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified and no active context.[/bold red]")
        raise typer.Exit(1)

    if csv_path is None:
        prospects_csv_path = get_campaign_scraped_data_dir(campaign_name) / "google_maps_prospects.csv"
    else:
        prospects_csv_path = csv_path
    
    if not prospects_csv_path.exists():
        console.print(f"[bold red]Prospects CSV not found at: {prospects_csv_path}[/bold red]")
        raise typer.Exit(code=1)

    console.print(f"[bold blue]Ingesting from: {prospects_csv_path} for campaign: {campaign_name}[/bold blue]")
    
    queue_manager = get_queue_manager("enrichment", use_cloud=True, campaign_name=campaign_name)
    existing_domains = {c.domain for c in Company.get_all() if c.domain} # Load existing companies once
    
    count = 0
    queued = 0
    
    with open(prospects_csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            count += 1
            try:
                valid_data = {k: v for k, v in row.items() if k in GoogleMapsProspect.model_fields}
                
                if not valid_data.get('Name') or not valid_data.get('Website') or not valid_data.get('Domain'):
                    logger.debug(f"Skipping row {count} due to missing Name, Website, or Domain: {row}")
                    continue

                prospect_data = GoogleMapsProspect.model_validate(valid_data)
                
                # 1. Import (Idempotent - creates/updates local file)
                # Note: import_prospect returns None if domain is in existing_domains
                company = import_prospect(prospect_data, campaign=campaign_name)
                
                domain = prospect_data.domain
                assert domain is not None # Ensure domain is not None for mypy
                # Calculate slug manually if company object is not returned
                from cocli.core.text_utils import slugify
                slug = company.slug if company else slugify(domain)

                # 2. Push to Queue (Always push for migration, or check if we want to skip processed)
                # For this migration, we assume we want to enrich everything in the CSV.
                # To prevent double-queueing in a single run, we can track local `queued_domains`
                
                msg = QueueMessage(
                    domain=domain,
                    company_slug=slug,
                    campaign_name=campaign_name,
                    force_refresh=force,
                    ttl_days=30, # Default
                    ack_token=None,
                )
                queue_manager.push(msg)
                queued += 1
                
                # Update existing_domains so import_prospect continues to skip duplicates in this run
                if domain:
                    existing_domains.add(domain)
                
                if queued % 100 == 0:
                    console.print(f"[cyan]Processed {count} rows, Queued {queued} tasks...[/cyan]")
                        
            except Exception as e:
                console.print(f"[bold red]Failed to ingest row {count} ({row.get('Name', 'N/A')}): {e}[/bold red]")
                logger.warning(f"Failed to ingest row {count}: {e}")
                
    console.print("[bold green]Ingestion Complete.[/bold green]")
    console.print(f"Total Rows Processed: {count}")
    console.print(f"Tasks Queued: {queued}")

if __name__ == "__main__":
    app()
