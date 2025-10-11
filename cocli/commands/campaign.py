
import typer
import toml
import csv
from pathlib import Path
from typing import List, Dict, Optional
import logging

from ..scrapers.google_maps import scrape_google_maps
from ..core.config import get_scraped_data_dir
from ..models.google_maps import GoogleMapsData
from ..core.config import get_campaign, set_campaign
from rich.console import Console
from ..core.campaign_workflow import CampaignWorkflow

logger = logging.getLogger(__name__)
app = typer.Typer(no_args_is_help=True)
console = Console()

@app.command()
def set(campaign_name: str = typer.Argument(..., help="The name of the campaign to set as the current context.")):
    """
    Sets the current campaign context.
    """
    set_campaign(campaign_name)
    workflow = CampaignWorkflow(campaign_name)
    console.print(f"[green]Campaign context set to:[/] [bold]{campaign_name}[/]")
    console.print(f"[green]Current workflow state for '{campaign_name}':[/] [bold]{workflow.state}[/]")

@app.command()
def unset():
    """
    Clears the current campaign context.
    """
    set_campaign(None)
    console.print("[green]Campaign context cleared.[/]")

@app.command()
def show():
    """
    Displays the current campaign context.
    """
    campaign_name = get_campaign()
    if campaign_name:
        console.print(f"Current campaign context is: [bold]{campaign_name}[/]")
    else:
        console.print("No campaign context is set.")

@app.command()
def status(
    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign to show status for. If not provided, uses the current campaign context.")
):
    """
    Displays the current state of the campaign workflow.
    """
    effective_campaign_name = campaign_name
    if effective_campaign_name is None:
        effective_campaign_name = get_campaign()
    
    if effective_campaign_name is None:
        console.print("[bold red]Error: No campaign name provided and no campaign context is set. Please provide a campaign name or set a campaign context using 'cocli campaign set <campaign_name>'.[/bold red]")
        raise typer.Exit(code=1)

    workflow = CampaignWorkflow(effective_campaign_name)
    console.print(f"[green]Current workflow state for '{effective_campaign_name}':[/] [bold]{workflow.state}[/]")

@app.command(name="start-workflow")
def start_workflow(
    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign to start the workflow for. If not provided, uses the current campaign context.")
):
    """
    Starts the campaign workflow.
    """
    effective_campaign_name = campaign_name
    if effective_campaign_name is None:
        effective_campaign_name = get_campaign()
    
    if effective_campaign_name is None:
        console.print("[bold red]Error: No campaign name provided and no campaign context is set. Please provide a campaign name or set a campaign context using 'cocli campaign set <campaign_name>'.[/bold red]")
        raise typer.Exit(code=1)

    workflow = CampaignWorkflow(effective_campaign_name)
    if workflow.state == 'idle':
        workflow.start_import()  # type: ignore
    else:
        console.print(f"[bold yellow]Workflow for '{effective_campaign_name}' is already in state '{workflow.state}'. Cannot start from idle.[/bold yellow]")

@app.command(name="next-step")
def next_step(
    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign to advance the workflow for. If not provided, uses the current campaign context.")
):
    """
    Advances the campaign workflow to the next logical step.
    """
    effective_campaign_name = campaign_name
    if effective_campaign_name is None:
        effective_campaign_name = get_campaign()
    
    if effective_campaign_name is None:
        console.print("[bold red]Error: No campaign name provided and no campaign context is set. Please provide a campaign name or set a campaign context using 'cocli campaign set <campaign_name>'.[/bold red]")
        raise typer.Exit(code=1)

    workflow = CampaignWorkflow(effective_campaign_name)
    current_state = workflow.state

    if current_state == 'idle':
        workflow.start_import()  # type: ignore
    elif current_state == 'import_customers':
        workflow.start_prospecting()  # type: ignore
    elif current_state == 'prospecting_scraping':
        workflow.finish_scraping()  # type: ignore
    elif current_state == 'prospecting_ingesting':
        workflow.finish_ingesting()  # type: ignore
    elif current_state == 'prospecting_importing':
        workflow.finish_prospecting_import()  # type: ignore
    elif current_state == 'prospecting_enriching':
        workflow.finish_enriching()  # type: ignore
    elif current_state == 'outreach':
        console.print("[bold yellow]Campaign is in outreach phase. Use specific outreach commands.[/bold yellow]")
    elif current_state == 'completed':
        console.print("[bold green]Campaign is already completed.[/bold green]")
    elif current_state == 'failed':
        console.print("[bold red]Campaign is in a failed state. Please review logs.[/bold red]")
    else:
        console.print(f"[bold yellow]No automatic next step defined for current state: {current_state}.[/bold yellow]")

@app.command()
def scrape_prospects(
    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign to scrape prospects for. If not provided, uses the current campaign context."),
    force_refresh: bool = typer.Option(False, "--force-refresh", help="Force re-scraping even if fresh data is in the cache."),
    ttl_days: int = typer.Option(30, "--ttl-days", help="Time-to-live for cached data in days."),
    max_results: int = typer.Option(30, "--max-results", help="Maximum number of results to scrape per query.")
):
    """
    Scrape prospects for a campaign from Google Maps, using a cache-first strategy.
    """
    if campaign_name is None:
        campaign_name = get_campaign()
        if campaign_name is None:
            logger.error("Error: No campaign name provided and no campaign context is set. Please provide a campaign name or set a campaign context using 'cocli campaign set <campaign_name>'.")
            raise typer.Exit(code=1)
    
    campaign_dirs = list(Path("campaigns").glob(f"**/{campaign_name}"))
    if not campaign_dirs:
        logger.error(f"Campaign '{campaign_name}' not found.")
        raise typer.Exit(code=1)
    campaign_dir = campaign_dirs[0]
    config_path = campaign_dir / "config.toml"
    
    if not config_path.exists():
        logger.error(f"Configuration file not found for campaign '{campaign_name}'.")
        raise typer.Exit(code=1)
        
    with open(config_path, "r") as f:
        config = toml.load(f)
        
    prospecting_config = config.get("prospecting", {})
    locations = prospecting_config.get("locations", [])
    queries = prospecting_config.get("queries", [])
    
    if not locations or not queries:
        logger.error("No locations or queries found in the prospecting configuration.")
        raise typer.Exit(code=1)
        
    output_dir = get_scraped_data_dir() / campaign_name / "prospects"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_filepath = output_dir / "prospects.csv"

    all_prospects: Dict[str, GoogleMapsData] = {}

    # Load existing prospects to avoid duplicates in the final list
    if output_filepath.exists():
        with open(output_filepath, "r", newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if row.get("Place_ID"):
                    # Re-create the model to ensure data consistency
                    model_data = {k: v for k, v in row.items() if k in GoogleMapsData.model_fields}
                    all_prospects[row["Place_ID"]] = GoogleMapsData(**model_data)

    for location in locations:
        for query in queries:
            logger.info(f"Scraping '{query}' in '{location}'...")
            scraped_data: List[GoogleMapsData] = scrape_google_maps(
                location_param={"city": location},
                search_string=query,
                force_refresh=force_refresh,
                ttl_days=ttl_days,
                max_results=max_results
            )

            for item in scraped_data:
                if item.Place_ID:
                    all_prospects[item.Place_ID] = item

    # Write all prospects (including old and new) to the CSV file
    with open(output_filepath, "w", newline="", encoding="utf-8") as csvfile:
        headers = GoogleMapsData.model_fields.keys()
        writer = csv.DictWriter(csvfile, fieldnames=headers)
        writer.writeheader()
        for item in all_prospects.values():
            writer.writerow(item.model_dump())
    
    logger.info(f"Prospecting complete. Results saved to {output_filepath}")
