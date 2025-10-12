import typer
import toml
import csv
from pathlib import Path
from typing import List, Dict, Optional
import logging

from ..scrapers.google_maps import scrape_google_maps
from ..core.config import get_scraped_data_dir, get_companies_dir
from ..models.google_maps import GoogleMapsData
from ..models.company import Company
from ..core.utils import slugify
import yaml
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
    console.print(f"[green]Campaign context set to:[/][bold]{campaign_name}[/]")
    console.print(f"[green]Current workflow state for '{campaign_name}':[/][bold]{workflow.state}[/]")

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
    console.print(f"[green]Current workflow state for '{effective_campaign_name}':[/][bold]{workflow.state}[/]")

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
def import_prospects(
    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign to import prospects for. If not provided, uses the current campaign context."),
):
    """
    Imports prospects from a campaign's prospects.csv into the canonical company structure.
    """
    if campaign_name is None:
        campaign_name = get_campaign()
        if campaign_name is None:
            logger.error("Error: No campaign name provided and no campaign context is set.")
            raise typer.Exit(code=1)

    console.print(f"[bold]Importing prospects for campaign: '{campaign_name}'[/bold]")

    prospects_csv_path = get_scraped_data_dir() / campaign_name / "prospects" / "prospects.csv"
    if not prospects_csv_path.exists():
        console.print(f"[bold red]Prospects CSV not found at: {prospects_csv_path}[/bold red]")
        raise typer.Exit(code=1)

    # Build a map of existing domains to prevent duplicates
    console.print("[dim]Building map of existing companies...[/dim]")
    existing_domains = {c.domain for c in Company.get_all() if c.domain}

    new_companies_imported = 0
    with open(prospects_csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            domain = row.get("Domain")
            if not domain or domain in existing_domains:
                continue

            # Map GoogleMapsData fields to Company fields
            company_data = {
                "name": row.get("Name"),
                "domain": domain,
                "full_address": row.get("Full_Address"),
                "phone_1": row.get("Phone"),
                "website_url": row.get("Website"),
                "categories": row.get("Category", "").split(';'),
                "reviews_count": int(row["Reviews_count"]) if row.get("Reviews_count") else None,
                "average_rating": float(row["Average_rating"]) if row.get("Average_rating") else None,
                "place_id": row.get("Place_ID"),
            }

            # Create a slug from the domain
            slug = slugify(domain)
            company_dir = get_companies_dir() / slug
            company_dir.mkdir(exist_ok=True)

            # Add prospect tag
            tags = ["prospect"]
            tags_path = company_dir / "tags.lst"
            with open(tags_path, 'w') as tags_file:
                tags_file.write("\n".join(tags))

            # Create and save the main company file
            index_path = company_dir / "_index.md"
            # Filter out None values before dumping to YAML
            frontmatter = {
                key: value for key, value in company_data.items() if value is not None
            }
            
            with open(index_path, 'w') as index_file:
                index_file.write("---\n")
                yaml.dump(frontmatter, index_file)
                index_file.write("---\n")

            console.print(f"[green]Imported new prospect:[/] {company_data['name']}")
            existing_domains.add(domain) # Add to set to avoid re-importing from same CSV
            new_companies_imported += 1

    console.print(f"[bold green]Import complete. Added {new_companies_imported} new companies.[/bold green]")


@app.command()
def scrape_prospects(
    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign to scrape prospects for. If not provided, uses the current campaign context."),
    force_refresh: bool = typer.Option(False, "--force-refresh", help="Force re-scraping even if fresh data is in the cache."),
    ttl_days: int = typer.Option(30, "--ttl-days", help="Time-to-live for cached data in days."),
    min_total_records: Optional[int] = typer.Option(None, "--min-total-records", help="Ensure the total number of prospects in the master list is at least this high."),
    max_new_records: Optional[int] = typer.Option(None, "--max-new-records", help="Scrape until this many *new* records are added in this session."),
    zoom_out_level: int = typer.Option(0, "--zoom-out-level", help="Number of times to zoom out on the map before scraping."),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run the browser in headless mode."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug mode for the scraper."),
):
    """
    Scrape prospects for a campaign from Google Maps, using a cache-first strategy.
    """
    if campaign_name is None:
        campaign_name = get_campaign()
        if campaign_name is None:
            logger.error("Error: No campaign name provided and no campaign context is set.")
            raise typer.Exit(code=1)
    
    if max_new_records is not None and min_total_records is not None:
        console.print("[bold red]Error: --min-total-records and --max-new-records cannot be used together.[/bold red]")
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

    if output_filepath.exists():
        with open(output_filepath, "r", newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if row.get("Place_ID"):
                    model_data = {k: v for k, v in row.items() if k in GoogleMapsData.model_fields}
                    all_prospects[row["Place_ID"]] = GoogleMapsData(**model_data)
    
    initial_prospect_count = len(all_prospects)
    new_records_goal = max_new_records

    if min_total_records is not None:
        if initial_prospect_count >= min_total_records:
            logger.info(f"Master prospect list already has {initial_prospect_count} records, which meets the target of {min_total_records}. Nothing to do.")
            return
        new_records_goal = min_total_records - initial_prospect_count
        logger.info(f"Need to find {new_records_goal} new records to meet the minimum total of {min_total_records}.")

    newly_added_count = 0
    for location in locations:
        if new_records_goal is not None and newly_added_count >= new_records_goal:
            break

        logger.info(f"--- Scraping all queries for location: '{location}' ---")
        
        scraper = scrape_google_maps(
            location_param={"city": location},
            search_strings=queries,
            campaign_name=campaign_name,
            debug=debug,
            force_refresh=force_refresh,
            ttl_days=ttl_days,
            headless=headless,
            zoom_out_level=zoom_out_level,
        )

        for item in scraper:
            if item.Place_ID and item.Place_ID not in all_prospects:
                all_prospects[item.Place_ID] = item
                newly_added_count += 1
                console.print(f"[green]Found new prospect: {item.Name} ({item.City}) ({newly_added_count}/{new_records_goal or 'N/A'})[/green]")
            
            if new_records_goal is not None and newly_added_count >= new_records_goal:
                logger.info(f"Target of {new_records_goal} new records met. Stopping scrape.")
                break

    # Write all prospects (including old and new) to the CSV file
    with open(output_filepath, "w", newline="", encoding="utf-8") as csvfile:
        headers = list(GoogleMapsData.model_fields.keys())
        writer = csv.DictWriter(csvfile, fieldnames=headers)
        writer.writeheader()
        for item in all_prospects.values():
            writer.writerow(item.model_dump())
    
    final_prospect_count = len(all_prospects)
    logger.info(f"Prospecting complete. Added {newly_added_count} new records. Total prospects: {final_prospect_count}. Results saved to {output_filepath}")