import typer
from pathlib import Path
from typing import Optional, List

from ..core.config import get_campaign, get_scraped_data_dir, get_companies_dir
from ..commands.campaign import scrape_prospects
from ..commands.ingest_google_maps_csv import google_maps_csv_to_google_maps_cache
from ..commands.import_companies import core_import_logic
from rich.console import Console

app = typer.Typer()
console = Console()

@app.command()
def process(
    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign to process Google Maps data for. If not provided, uses the current campaign context."),
    force_refresh: bool = typer.Option(False, "--force-refresh", help="Force re-scraping even if fresh data is in the cache."),
    skip_scrape: bool = typer.Option(False, "--skip-scrape", help="Skip the scraping step."),
    skip_ingest: bool = typer.Option(False, "--skip-ingest", help="Skip the ingestion step."),
    skip_import: bool = typer.Option(False, "--skip-import", help="Skip the import step."),
    cleanup_csv: bool = typer.Option(False, "--cleanup-csv", help="Delete the scraped CSV file after successful processing."),
    ttl_days: int = typer.Option(30, "--ttl-days", help="Time-to-live for cached data in days (for scraping).")
):
    """
    Processes Google Maps data for a campaign: scrapes, ingests, and imports.
    """
    effective_campaign_name = campaign_name
    if effective_campaign_name is None:
        effective_campaign_name = get_campaign()
    
    if effective_campaign_name is None:
        console.print("[bold red]Error: No campaign name provided and no campaign context is set. Please provide a campaign name or set a campaign context using 'cocli campaign set <campaign_name>'.[/bold red]")
        raise typer.Exit(code=1)

    console.print(f"[bold green]Processing Google Maps data for campaign: {effective_campaign_name}[/bold green]")

    scraped_csv_path = get_scraped_data_dir() / effective_campaign_name / "prospects" / "prospects.csv"

    # 1. Scrape Prospects
    if not skip_scrape:
        console.print("[bold blue]Step 1: Scraping prospects...[/bold blue]")
        try:
            scrape_prospects(
                campaign_name=effective_campaign_name,
                force_refresh=force_refresh,
                ttl_days=ttl_days
            )
            console.print("[bold green]Scraping complete.[/bold green]")
        except typer.Exit as e:
            if e.code == 1: # Exit code 1 for "Campaign not found" or "No locations/queries"
                console.print(f"[bold yellow]Scraping skipped due to configuration issues or no data: {e.message}[/bold yellow]")
            else:
                console.print(f"[bold red]Scraping failed: {e.message}[/bold red]")
                raise
        except Exception as e:
            console.print(f"[bold red]An unexpected error occurred during scraping: {e}[/bold red]")
            raise
    else:
        console.print("[bold yellow]Scraping step skipped.[/bold yellow]")

    # Ensure CSV exists for subsequent steps
    if not scraped_csv_path.exists():
        console.print(f"[bold red]Error: Scraped CSV file not found at {scraped_csv_path}. Cannot proceed with ingestion/import.[/bold red]")
        raise typer.Exit(code=1)

    # 2. Ingest Google Maps CSV
    if not skip_ingest:
        console.print("[bold blue]Step 2: Ingesting Google Maps CSV...[/bold blue]")
        try:
            google_maps_csv_to_google_maps_cache(csv_path=scraped_csv_path)
            console.print("[bold green]Ingestion complete.[/bold green]")
        except Exception as e:
            console.print(f"[bold red]Ingestion failed: {e}[/bold red]")
            raise
    else:
        console.print("[bold yellow]Ingestion step skipped.[/bold yellow]")

    # 3. Import Companies
    if not skip_import:
        console.print("[bold blue]Step 3: Importing companies...[/bold blue]")
        try:
            core_import_logic(
                prospects_csv_path=scraped_csv_path,
                tags=["prospect", effective_campaign_name],
                companies_dir=get_companies_dir() # Pass the companies_dir directly
            )
            console.print("[bold green]Import complete.[/bold green]")
        except Exception as e:
            console.print(f"[bold red]Import failed: {e}[/bold red]")
            raise
    else:
        console.print("[bold yellow]Import step skipped.[/bold yellow]")

    # 4. Cleanup
    if cleanup_csv:
        console.print(f"[bold blue]Cleaning up scraped CSV file: {scraped_csv_path}[/bold blue]")
        try:
            scraped_csv_path.unlink()
            console.print("[bold green]CSV cleanup complete.[/bold green]")
        except Exception as e:
            console.print(f"[bold red]CSV cleanup failed: {e}[/bold red]")
            # Do not re-raise, as the main process is complete
    
    console.print(f"[bold green]Google Maps processing for campaign '{effective_campaign_name}' finished successfully.[/bold green]")
