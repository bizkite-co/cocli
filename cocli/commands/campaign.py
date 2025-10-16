import typer
import toml
import csv
import asyncio
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import logging
import httpx

from ..scrapers.google_maps import scrape_google_maps
from ..core.config import get_scraped_data_dir, get_companies_dir, get_cocli_base_dir, get_campaign_dir
from ..core.geocoding import get_coordinates_from_city_state
from ..models.google_maps import GoogleMapsData
from ..models.company import Company
from ..models.website import Website
from ..core.utils import slugify
import yaml
from ..models.google_maps import GoogleMapsData
from ..core.config import get_campaign, set_campaign
from rich.console import Console
from ..core.campaign_workflow import CampaignWorkflow
from ..core.enrichment import enrich_company_website
from ..core.logging_config import setup_file_logging
from ..compilers.website_compiler import WebsiteCompiler
from ..core.scrape_index import ScrapeIndex

from typing_extensions import Annotated
from cocli.models.campaign import Campaign
from cocli.core.config import get_cocli_base_dir

app = typer.Typer()

@app.command()
def add(
    name: Annotated[str, typer.Argument(help="The name of the campaign.")],
    company: Annotated[str, typer.Argument(help="The name of the company.")],
):
    """
    Adds a new campaign.
    """
    data_home = get_cocli_base_dir()
    try:
        Campaign.create(name, company, data_home)
        print(f"Campaign '{name}' created successfully.")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise typer.Exit(code=1)

from . import prospects
app.add_typer(prospects.app, name="prospects")

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
from ..core.importing import import_prospect

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
            # Create a GoogleMapsData object from the CSV row
            model_data = {k: v for k, v in row.items() if k in GoogleMapsData.model_fields}
            prospect_data = GoogleMapsData(**model_data)

            # Call the core import function
            new_company = import_prospect(prospect_data, existing_domains)

            if new_company:
                console.print(f"[green]Imported new prospect:[/] {new_company.name}")
                if new_company.domain:
                    existing_domains.add(new_company.domain) # Add to set to avoid re-importing from same CSV
                new_companies_imported += 1

    console.print(f"[bold green]Import complete. Added {new_companies_imported} new companies.[/bold green]")
from playwright.async_api import async_playwright

@app.command()
async def achieve_goal(

    goal_emails: int = typer.Option(10, "--emails", help="The number of new companies with emails to find."),

    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign to run. If not provided, uses the current campaign context."),

    zoom_out_level: int = typer.Option(3, help="How many times to zoom out to set the initial search area."),

    force: bool = typer.Option(False, "--force", "-f", help="Force enrichment of all companies, even if they have fresh data."),

    ttl_days: int = typer.Option(30, "--ttl-days", help="Time-to-live for cached data in days."),

    headed: bool = typer.Option(False, "--headed", help="Run the browser in headed mode."),

    devtools: bool = typer.Option(False, "--devtools", help="Open browser with devtools open."),

    debug: bool = typer.Option(False, "--debug", help="Enable debug mode with breakpoints."),

):

    """

    Runs the entire prospecting pipeline until a specified goal is achieved.

    """

    if campaign_name is None:

        campaign_name = get_campaign()

        if campaign_name is None:

            logger.error("Error: No campaign name provided and no campaign context is set.")

            raise typer.Exit(code=1)

    # --- Health Check for Enrichment Service ---

    console.print(f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [dim]Pinging enrichment service...[/dim]")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8000/health", timeout=5.0)

            response.raise_for_status()

        console.print(f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [green]Enrichment service is online.[/green]")

    except httpx.RequestError as e:

        console.print("[bold red]Error: Could not connect to the enrichment service.[/bold red]")

        console.print(f"[red]Please ensure the Docker container is running: 'docker run -d -p 8000:8000 --name cocli-enrichment enrichment-service'[/red]")

        console.print(f"[dim]Details: {e}[/dim]")

        raise typer.Exit(code=1)

    console.print(f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [bold]Achieving goal for campaign: '{campaign_name}'[/bold]")

    console.print(f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [bold]Goal:[/] Find {goal_emails} new companies with emails.")    # --- Load Campaign Config ---

    campaign_dir = get_campaign_dir(campaign_name)

    if not campaign_dir:

        logger.error(f"Campaign '{campaign_name}' not found.")

        raise typer.Exit(code=1)

    config_path = campaign_dir / "config.toml"
    if not config_path.exists():

        logger.error(f"Configuration file not found for campaign '{campaign_name}'.")

        raise typer.Exit(code=1)
    with open(config_path, "r") as f:        config = toml.load(f)
    prospecting_config = config.get("prospecting", {})
    locations = prospecting_config.get("locations", [])
    search_phrases = prospecting_config.get("queries", [])
    if not locations or not search_phrases:
        logger.error("No locations or queries found in the prospecting configuration.")

        raise typer.Exit(code=1)    # --- Setup ---

    setup_file_logging(f"{campaign_name}-achieve-goal", console_level=logging.WARNING, disable_console=False)

    console.print(f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [dim]Building map of existing companies...[/dim]")

    existing_domains = {c.domain for c in Company.get_all() if c.domain}

    emails_found_count = 0    # --- Main Pipeline Loop ---

    async def pipeline():
        nonlocal emails_found_count
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=not headed, devtools=devtools)
            try:
                for location in locations:
                    if emails_found_count >= goal_emails:
                        break
                    coords = get_coordinates_from_city_state(location)
                    if coords:
                        console.print(f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [bold blue]-- Starting location: {location} ({coords['latitude']:.4f}, {coords['longitude']:.4f}) --[/bold blue]")
                    else:
                        console.print(f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [bold blue]-- Starting location: {location} (Coordinates not found) --[/bold blue]")
                    # 1. Scrape (Generator)

                    prospect_generator = scrape_google_maps(

                        browser=browser,
                        location_param={"city": location},

                        search_strings=search_phrases,

                        campaign_name=campaign_name,
                        zoom_out_level=zoom_out_level,

                        force_refresh=force,
                        ttl_days=ttl_days,
                        debug=debug
                    )
                    async for prospect_data in prospect_generator:
                        # 2. Import
                        company = import_prospect(prospect_data, existing_domains)
                        if not company or not company.domain:
                            continue # Skip duplicates or prospects without a domain
                        console.print(
                            f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [cyan]New prospect imported:[/] {company.name}"
                        )
                        existing_domains.add(company.domain) # Add to set to avoid re-importing from same CSV
                        # 3. Enrich (via Service)
                        website_data = None
                        async with httpx.AsyncClient() as client:
                            try:
                                response = await client.post(
                                    "http://localhost:8000/enrich",
                                    json={
                                        "domain": company.domain,
                                        "force": force,
                                        "ttl_days": ttl_days,
                                        "debug": debug
                                    },
                                    timeout=120.0  # Generous timeout for scraping
                                )
                                response.raise_for_status()  # Raise exception for 4xx/5xx
                                # Assuming the service returns a dict that can be loaded into the Website model
                                response_json = response.json()
                                if response_json: # Check if response is not empty
                                    website_data = Website(**response_json)
                            except httpx.RequestError as e:                                logger.error(f"HTTP request to enrichment service failed for {company.domain}: {e}")
                            except Exception as e:
                                logger.error(f"Error processing enrichment response for {company.domain}: {e}")
                        if website_data and website_data.email:
                            console.print(f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [green]   -> Found email: {website_data.email}[/green]")
                            # Save enrichment data and compile
                            company_dir = get_companies_dir() / company.slug
                            enrichment_dir = company_dir / "enrichments"
                            website_md_path = enrichment_dir / "website.md"
                            website_data.associated_company_folder = company_dir.name
                            enrichment_dir.mkdir(parents=True, exist_ok=True)
                            with open(website_md_path, "w") as f:
                                f.write("---")
                                yaml.dump(website_data.model_dump(exclude_none=True), f, sort_keys=False, default_flow_style=False, allow_unicode=True)
                                f.write("---")
                            compiler = WebsiteCompiler()
                            compiler.compile(company_dir)
                            emails_found_count += 1
                            console.print(f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [bold green]Progress: {emails_found_count} / {goal_emails} emails found.[/bold green]")
                        else:
                            console.print(f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [yellow] -> No email found for {company.name}[/yellow]")
                            # 4. Check Goal
                            if emails_found_count >= goal_emails:
                                console.print(f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [bold magenta]Goal of {goal_emails} emails met. Stopping search.[/bold magenta]")
                                break
            finally:
                await browser.close()
    # Run the async pipeline
    await pipeline()
    console.print(f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [bold blue]Pipeline finished.[/bold blue]")@app.command(name="visualize-coverage")
def visualize_coverage(
    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign to visualize. If not provided, uses the current campaign context."),
    output_file: Path = typer.Option("coverage.kml", "--output", "-o", help="The path to save the KML file."),
):
    """
    Generates a KML file to visualize the scraped areas for a campaign.
    """
    if campaign_name is None:
        campaign_name = get_campaign()
        if campaign_name is None:
            logger.error("Error: No campaign name provided and no campaign context is set.")
            raise typer.Exit(code=1)

    console.print(f"[bold]Generating coverage visualization for campaign: '{campaign_name}'[/bold]")

    try:
        scrape_index = ScrapeIndex(campaign_name)
        if not scrape_index._index:
            console.print("[yellow]Scrape index is empty. No coverage to visualize.[/yellow]")
            return
    except FileNotFoundError:
        console.print(f"[bold red]Scrape index file not found for campaign '{campaign_name}'.[/bold red]")
        console.print(f"[dim]Looked for: {get_cocli_base_dir() / 'indexes' / campaign_name / 'scraped_areas.csv'}[/dim]")
        raise typer.Exit(code=1)

    # Assign colors to phrases
    phrases = sorted(list({area.phrase for area in scrape_index._index}))
    colors = ["ff0000ff", "ff00ff00", "ffff0000", "ff00ffff", "ffff00ff", "ffffff00"] # Red, Green, Blue, Cyan, Magenta, Yellow
    phrase_colors = {phrase: colors[i % len(colors)] for i, phrase in enumerate(phrases)}

    kml_placemarks = []
    for area in scrape_index._index:
        coordinates = (
            f"{area.lon_min},{area.lat_min},0 "
            f"{area.lon_max},{area.lat_min},0 "
            f"{area.lon_max},{area.lat_max},0 "
            f"{area.lon_min},{area.lat_max},0 "
            f"{area.lon_min},{area.lat_min},0"
        )
        placemark = f'''        <Placemark>
            <name>{area.phrase}</name>
            <description>Scraped on {area.scrape_date.strftime('%Y-%m-%d')}</description>
            <Style>
                <LineStyle>
                    <color>{phrase_colors.get(area.phrase, 'ffffffff')}</color>
                    <width>2</width>
                </LineStyle>
                <PolyStyle>
                    <color>80{phrase_colors.get(area.phrase, 'ffffffff')[2:]}</color>  <!-- 50% opacity -->
                </PolyStyle>
            </Style>
            <Polygon>
                <outerBoundaryIs>
                    <LinearRing>
                        <coordinates>{coordinates}</coordinates>
                    </LinearRing>
                </outerBoundaryIs>
            </Polygon>
        </Placemark> '''
        kml_placemarks.append(placemark)

    kml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
    <Document>
        <name>Scrape Coverage for {campaign_name}</name>
{"\n".join(kml_placemarks)}
    </Document>
</kml>'''

    try:
        with open(output_file, 'w') as f:
            f.write(kml_content)
        console.print(f"[bold green]Successfully generated KML file at: {output_file.absolute()}[/bold green]")
    except IOError as e:
        console.print(f"[bold red]Error writing to file {output_file}: {e}[/bold red]")
        raise typer.Exit(code=1)
