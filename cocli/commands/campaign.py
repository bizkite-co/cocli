from playwright.async_api import async_playwright
from ..core.importing import import_prospect
import typer
import toml
import csv
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, Set
from datetime import datetime
import logging
import re
import math
import pandas as pd
import httpx

from ..models.website import Website
from ..scrapers.google_maps import scrape_google_maps

from ..core.config import get_scraped_data_dir, get_companies_dir, get_campaign_dir, get_cocli_base_dir, get_people_dir, get_all_campaign_dirs, get_editor_command
from ..core.geocoding import get_coordinates_from_city_state
from ..models.google_maps import GoogleMapsData
from ..models.company import Company
from ..models.person import Person
import yaml
from ..core.config import get_campaign, set_campaign
from rich.console import Console
from ..renderers.campaign_view import display_campaign_view
from ..core.campaign_workflow import CampaignWorkflow
from ..core.logging_config import setup_file_logging
from ..compilers.website_compiler import WebsiteCompiler
from ..core.scrape_index import ScrapeIndex
from ..core.location_prospects_index import LocationProspectsIndex
from cocli.core.enrichment_service_utils import ensure_enrichment_service_ready
from cocli.models.campaign import Campaign
from ..core.utils import run_fzf, slugify

from typing_extensions import Annotated

from . import prospects

logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer(no_args_is_help=True, invoke_without_command=True)

@app.callback()
def campaign(ctx: typer.Context) -> None:
    """
    Manage campaigns.
    """
    if ctx.invoked_subcommand is None:
        show()

@app.command()
def edit(
    campaign_name: Annotated[Optional[str], typer.Argument(help="The name of the campaign to edit.")] = None
) -> None:
    """
    Edits an existing campaign's configuration.
    """
    if campaign_name is None:
        campaign_dirs = get_all_campaign_dirs()
        if not campaign_dirs:
            console.print("[bold red]No campaigns found.[/bold red]")
            raise typer.Exit(code=1)
        
        campaign_names = [d.name for d in campaign_dirs]
        fzf_input = "\n".join(campaign_names)
        selected_campaign = run_fzf(fzf_input)
        
        if not selected_campaign:
            console.print("No campaign selected.")
            raise typer.Exit(code=1)
        campaign_name = selected_campaign

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[bold red]Campaign '{campaign_name}' not found.[/bold red]")
        raise typer.Exit(code=1)

    config_path = campaign_dir / "config.toml"
    readme_path = campaign_dir / "README.md"

    editor_command = get_editor_command()

    if editor_command:
        files_to_edit = []
        if config_path.exists():
            files_to_edit.append(str(config_path))
        else:
            console.print(f"[bold red]Configuration file not found for campaign '{campaign_name}'.[/bold red]")

        if readme_path.exists():
            files_to_edit.append(str(readme_path))

        if not files_to_edit:
            console.print(f"[bold red]No files to edit for campaign '{campaign_name}'.[/bold red]")
            raise typer.Exit(code=1)

        command = [editor_command]
        # For vim/nvim, use -o for horizontal split
        if "vim" in editor_command or "nvim" in editor_command:
            command.append("-o")
        
        command.extend(files_to_edit)
        
        subprocess.run(command)
    else:
        if config_path.exists():
            typer.edit(filename=str(config_path))
        else:
            console.print(f"[bold red]Configuration file not found for campaign '{campaign_name}'.[/bold red]")

        if readme_path.exists():
            console.print("[yellow]To edit the README.md as well, please configure an editor in your cocli_config.toml.[/yellow]")

@app.command()
def add(
    name: Annotated[str, typer.Argument(help="The name of the campaign.")],
    company: Annotated[str, typer.Argument(help="The name of the company.")],
) -> None:
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

app.add_typer(prospects.app, name="prospects")

console = Console()

@app.command()
def set(campaign_name: str = typer.Argument(..., help="The name of the campaign to set as the current context.")) -> None:
    """
    Sets the current campaign context.
    """
    set_campaign(campaign_name)
    workflow = CampaignWorkflow(campaign_name)
    console.print(f"[green]Campaign context set to:[/][bold]{campaign_name}[/]")
    console.print(f"[green]Current workflow state for '{campaign_name}':[/][bold]{workflow.state}[/]")


@app.command(name="import-contacts")
def import_contacts(
    csv_path: Path = typer.Argument(..., help="Path to the CSV file containing contacts."),
    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign to import contacts into. If not provided, uses the current campaign context."),
) -> None:
    """
    Imports contacts from a CSV file into a campaign.

    The CSV file should have the following headers:
    name, email, phone, company_name, role, tags, full_address, street_address, city, state, zip_code, country
    """
    if campaign_name is None:
        campaign_name = get_campaign()
        if campaign_name is None:
            logger.error("Error: No campaign name provided and no campaign context is set.")
            raise typer.Exit(code=1)

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[bold red]Campaign '{campaign_name}' not found.[/bold red]")
        raise typer.Exit(code=1)

    contacts_dir = campaign_dir / "contacts"
    contacts_dir.mkdir(exist_ok=True)

    people_dir = get_people_dir()

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                person = Person.model_validate(row)
                person_slug = slugify(person.name)
                person_dir = people_dir / person_slug
                person_dir.mkdir(exist_ok=True)

                person_file = person_dir / f"{person_slug}.md"
                with open(person_file, "w") as pf:
                    pf.write("---")
                    yaml.dump(person.model_dump(exclude_none=True), pf, sort_keys=False, default_flow_style=False, allow_unicode=True)
                    pf.write("---")

                symlink_path = contacts_dir / person_slug
                if not symlink_path.exists():
                    symlink_path.symlink_to(person_dir)
                
                console.print(f"[green]Imported contact:[/] {person.name}")

            except Exception as e:
                console.print(f"[bold red]Error importing contact: {e}[/bold red]")


@app.command()
def unset() -> None:
    """
    Clears the current campaign context.
    """
    set_campaign(None)
    console.print("[green]Campaign context cleared.[/]")


@app.command()
def show() -> None:
    """
    Displays the current campaign context.
    """
    campaign_name = get_campaign()
    if campaign_name:
        campaign_dir = get_campaign_dir(campaign_name)
        if not campaign_dir:
            console.print(f"[bold red]Campaign '{campaign_name}' not found.[/bold red]")
            raise typer.Exit(code=1)

        config_path = campaign_dir / "config.toml"
        if not config_path.exists():
            console.print(f"[bold red]Configuration file not found for campaign '{campaign_name}'.[/bold red]")
            raise typer.Exit(code=1)

        with open(config_path, "r") as f:
            config_data = toml.load(f)
        
        # The campaign data is under a 'campaign' key in the TOML file,
        # and other sections are at the top level. We need to flatten it.
        flat_config = config_data.pop('campaign')
        flat_config.update(config_data)

        try:
            campaign = Campaign.model_validate(flat_config)
        except Exception as e:
            console.print(f"[bold red]Error validating campaign configuration for '{campaign_name}': {e}[/bold red]")
            raise typer.Exit(code=1)

        display_campaign_view(console, campaign)
    else:
        console.print("No campaign context is set.")

@app.command()
def status(
    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign to show status for. If not provided, uses the current campaign context.")
) -> None:
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
) -> None:
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
) -> None:
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
) -> None:
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
            prospect_data = GoogleMapsData.model_validate(model_data)

            # Call the core import function
            new_company = import_prospect(prospect_data, existing_domains, campaign=campaign_name)

            if new_company:
                console.print(f"[green]Imported new prospect:[/] {new_company.name}")
                if new_company.domain:
                    existing_domains.add(new_company.domain) # Add to set to avoid re-importing from same CSV
                new_companies_imported += 1

    console.print(f"[bold green]Import complete. Added {new_companies_imported} new companies.[/bold green]")

async def pipeline(
    locations: list[str],
    search_phrases: list[str],
    goal_emails: int,
    headed: bool,
    devtools: bool,
    campaign_name: str,
    zoom_out_button_selector: str,
    panning_distance_miles: int,
    initial_zoom_out_level: int,
    omit_zoom_feature: bool,
    force: bool,
    ttl_days: int,
    debug: bool,
    existing_domains: Set[str],
    console: Console,
    browser_width: int,
    browser_height: int,
    location_prospects_index: LocationProspectsIndex,
) -> None:
    emails_found_count = 0

    prospects_csv_path = get_scraped_data_dir() / campaign_name / "prospects" / "prospects.csv"
    prospects_csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not prospects_csv_path.exists()

    with open(prospects_csv_path, 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=GoogleMapsData.model_fields.keys())
        if write_header:
            writer.writeheader()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=not headed, devtools=devtools)
            try:
                # Initialize location data with current prospect counts
                location_data = []
                for loc_name in locations:
                    current_prospects = location_prospects_index.get_prospect_count(loc_name)
                    location_data.append({"name": loc_name, "prospect_count": current_prospects})

                # Convert to DataFrame for easy sorting
                location_df = pd.DataFrame(location_data)

                while emails_found_count < goal_emails:
                    # Sort locations by prospect count (least prospected first)
                    location_df = location_df.sort_values(by="prospect_count", ascending=True).reset_index(drop=True)

                    # Select the top 3 least prospected locations, or fewer if less than 3 are available
                    num_locations_to_process = min(3, len(location_df))
                    if num_locations_to_process == 0:
                        console.print("[bold red]No locations to process. Exiting.[/bold red]")
                        break

                    selected_locations = location_df.head(num_locations_to_process)

                    # Calculate emails to scrape per selected location
                    remaining_emails = goal_emails - emails_found_count
                    emails_per_location = math.ceil(remaining_emails / num_locations_to_process)

                    console.print(f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [bold yellow]Targeting {num_locations_to_process} least prospected locations. Aiming for ~{emails_per_location} emails per location.[/bold yellow]")

                    for _, loc_row in selected_locations.iterrows():
                        location = str(loc_row["name"])
                        if emails_found_count >= goal_emails:
                            break

                        coords = get_coordinates_from_city_state(location)
                        if coords:
                            console.print(
                                f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [bold blue]-- Starting location: {location} ({coords['latitude']:.4f}, {coords['longitude']:.4f}) --[/bold blue]"
                            )
                        else:
                            console.print(
                                f"[grey50][{datetime.now().strftime('%H:%M:%S')}] [/] [bold blue]-- Starting location: {location} (Coordinates not found) --[/bold blue]"
                            )
                            continue

                        # 1. Scrape (Generator)
                        prospect_generator = scrape_google_maps(
                            browser=browser,
                            location_param={"city": location},
                            search_strings=search_phrases,
                            campaign_name=campaign_name,
                            zoom_out_button_selector=zoom_out_button_selector,
                            panning_distance_miles=panning_distance_miles,
                            initial_zoom_out_level=initial_zoom_out_level,
                            omit_zoom_feature=omit_zoom_feature,
                            force_refresh=force,
                            ttl_days=ttl_days,
                            debug=debug,
                            browser_width=browser_width,
                            browser_height=browser_height,
                        )
                        
                        scraped_from_current_location = 0
                        async for prospect_data in prospect_generator:
                            # Write to CSV
                            writer.writerow(prospect_data.model_dump())

                            # 2. Import
                            company = import_prospect(prospect_data, existing_domains, campaign=campaign_name)
                            if not company or not company.domain:
                                continue  # Skip duplicates or prospects without a domain
                            console.print(
                                f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [cyan]New prospect imported:[/] {company.name}"
                            )
                            existing_domains.add(
                                company.domain
                            )  # Add to set to avoid re-importing from same CSV
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
                                            "debug": debug,
                                            "campaign_name": campaign_name,
                                        },
                                        timeout=120.0,  # Generous timeout for scraping
                                    )
                                    response.raise_for_status()  # Raise exception for 4xx/5xx
                                    # Assuming the service returns a dict that can be loaded into the Website model
                                    response_json = response.json()
                                    if response_json:  # Check if response is not empty
                                        # Pre-process personnel field if it's malformed
                                        if "personnel" in response_json and isinstance(response_json["personnel"], list):
                                            processed_personnel = []
                                            for item in response_json["personnel"]:
                                                if isinstance(item, str):
                                                    # Attempt to parse email from string
                                                    email_match = re.search(r'Email:\s*(\S+@\S+)', item)
                                                    if email_match:
                                                        processed_personnel.append({"email": email_match.group(1).replace(" ", "")})
                                                    else:
                                                        logger.warning(f"Could not parse personnel string into dictionary: {item}")
                                                elif isinstance(item, dict):
                                                    processed_personnel.append(item)
                                                else:
                                                    logger.warning(f"Unexpected type for personnel item: {type(item)}. Skipping.")
                                            response_json["personnel"] = processed_personnel
                                        elif "personnel" in response_json and isinstance(response_json["personnel"], str):
                                            # Handle the case where personnel itself is a single string
                                            email_match = re.search(r'Email:\s*(\S+@\S+)', response_json["personnel"])
                                            if email_match:
                                                response_json["personnel"] = [{"email": email_match.group(1).replace(" ", "")}]
                                            else:
                                                logger.warning(f"Could not parse personnel string into dictionary: {response_json['personnel']}. Setting to empty list.")
                                                response_json["personnel"] = []
                                        elif "personnel" not in response_json:
                                            response_json["personnel"] = [] # Ensure personnel field exists as a list

                                        website_data = Website(**response_json)
                                except httpx.RequestError as e:
                                    logger.error(
                                        f"HTTP request to enrichment service failed for {company.domain}: {e}"
                                    )
                                except Exception as e:
                                    logger.error(
                                        f"Error processing enrichment response for {company.domain}: {e}"
                                    )
                            if website_data and website_data.email:
                                console.print(
                                    f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [green]   -> Found email: {website_data.email}[/green]"
                                )
                                # Save enrichment data and compile
                                if company.slug is None:
                                    logger.warning(f"Skipping enrichment data save for company {company.name} due to missing slug.")
                                    continue
                                company_dir = get_companies_dir() / company.slug
                                enrichment_dir = company_dir / "enrichments"
                                website_md_path = enrichment_dir / "website.md"
                                website_data.associated_company_folder = company_dir.name
                                enrichment_dir.mkdir(parents=True, exist_ok=True)
                                with open(website_md_path, "w") as f:
                                    f.write("---")
                                    yaml.dump(
                                        website_data.model_dump(exclude_none=True),
                                        f,
                                        sort_keys=False,
                                        default_flow_style=False,
                                        allow_unicode=True,
                                    )
                                    f.write("---")
                                compiler = WebsiteCompiler()
                                compiler.compile(company_dir)
                                emails_found_count += 1
                                scraped_from_current_location += 1
                                location_prospects_index.update_prospect_count(location, 1)
                                # Update the DataFrame for the current location
                                location_df.loc[location_df["name"] == location, "prospect_count"] += 1
                                console.print(
                                    f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [bold green]Progress: {emails_found_count} / {goal_emails} emails found.[/bold green]"
                                )
                            else:
                                console.print(
                                    f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [yellow] -> No email found for {company.name}[/yellow]"
                                )
                                # 4. Check Goal
                                if emails_found_count >= goal_emails:
                                    console.print(
                                        f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [bold magenta]Goal of {goal_emails} emails met. Stopping search.[/bold magenta]"
                                    )
                                    break
                            
                            # Stop scraping from current location if we've met its quota or overall goal
                            if scraped_from_current_location >= emails_per_location or emails_found_count >= goal_emails:
                                break
                    
                    if emails_found_count >= goal_emails:
                        break

            finally:
                await browser.close()


@app.command()
def achieve_goal(

    goal_emails: int = typer.Option(10, "--emails", help="The number of new companies with emails to find."),

    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign to run. If not provided, uses the current campaign context."),

    force: bool = typer.Option(False, "--force", "-f", help="Force enrichment of all companies, even if they have fresh data."),

    ttl_days: int = typer.Option(30, "--ttl-days", help="Time-to-live for cached data in days."),

    headed: bool = typer.Option(False, "--headed", help="Run the browser in headed mode."),

    devtools: bool = typer.Option(False, "--devtools", help="Open browser with devtools open."),

    debug: bool = typer.Option(False, "--debug", help="Enable debug mode with breakpoints."),

    browser_width: int = typer.Option(2000, help="The width of the browser viewport."),

    browser_height: int = typer.Option(1500, help="The height of the browser viewport."),

) -> None:

    """

    Runs the entire prospecting pipeline until a specified goal is achieved.

    """

    console = Console()

    if campaign_name is None:
        campaign_name = get_campaign()
        if campaign_name is None:
            logger.error("Error: No campaign name provided and no campaign context is set.")
            raise typer.Exit(code=1)

    ensure_enrichment_service_ready(console)

    console.print(
        f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [bold]Achieving goal for campaign: '{campaign_name}'[/bold]"
    )

    console.print(
        f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [bold]Goal:[/bold] Find {goal_emails} new companies with emails."
    )
    if goal_emails > 0:
        console.print(
            f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [yellow]Note: The 'achieve-goal' pipeline runs sequentially when a specific email goal is set, processing one prospect at a time through Google Maps scraping and website enrichment.[/yellow]"
        )  # --- Load Campaign Config ---

    campaign_dir = get_campaign_dir(campaign_name)

    if not campaign_dir:

        logger.error(f"Campaign '{campaign_name}' not found.")

        raise typer.Exit(code=1)

    assert campaign_name is not None # mypy needs this to understand campaign_name is not None here

    config_path = campaign_dir / "config.toml"
    if not config_path.exists():

        logger.error(f"Configuration file not found for campaign '{campaign_name}'.")

        raise typer.Exit(code=1)
    with open(config_path, "r") as f:
        config = toml.load(f)
    prospecting_config = config.get("prospecting", {})
    locations = prospecting_config.get("locations", [])
    search_phrases = prospecting_config.get("queries", [])
    zoom_out_button_selector = prospecting_config.get("zoom-out-button-selector", "div#zoomOutButton")
    panning_distance_miles = prospecting_config.get("panning-distance-miles", 8)
    initial_zoom_out_level = prospecting_config.get("initial-zoom-out-level", 3)
    omit_zoom_feature = prospecting_config.get("omit-zoom-feature", False)

    if not locations or not search_phrases:
        logger.error("No locations or queries found in the prospecting configuration.")

        raise typer.Exit(code=1)  # --- Setup ---

    setup_file_logging(f"{campaign_name}-achieve-goal", console_level=logging.WARNING, disable_console=False)

    console.print(
        f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [dim]Building map of existing companies...[/dim]"
    )

    existing_domains = {c.domain for c in Company.get_all() if c.domain}

    location_prospects_index = LocationProspectsIndex(campaign_name=campaign_name)

    # --- Main Pipeline Loop ---
    asyncio.run(
        pipeline(
            locations=locations,
            search_phrases=search_phrases,
            goal_emails=goal_emails,
            headed=headed,
            devtools=devtools,
            campaign_name=campaign_name,
            zoom_out_button_selector=zoom_out_button_selector,
            panning_distance_miles=panning_distance_miles,
            initial_zoom_out_level=initial_zoom_out_level,
            omit_zoom_feature=omit_zoom_feature,
            force=force,
            ttl_days=ttl_days,
            debug=debug,
            existing_domains=existing_domains,
            console=console,
            browser_width=browser_width,
            browser_height=browser_height,
            location_prospects_index=location_prospects_index,
        )
    )
    message = f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [bold blue]Pipeline finished.[/bold blue]"
    console.print(message)


@app.command(name="visualize-coverage")
def visualize_coverage(
    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign to visualize. If not provided, uses the current campaign context."),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="The path to save the KML file. Defaults to coverage.kml in the campaign directory."),
) -> None:
    """
    Generates a KML file to visualize the scraped areas for a campaign.
    """
    if campaign_name is None:
        campaign_name = get_campaign()
        if campaign_name is None:
            logger.error("Error: No campaign name provided and no campaign context is set.")
            raise typer.Exit(code=1)

    console.print(f"[bold]Generating coverage visualization for campaign: '{campaign_name}'[/bold]")

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[bold red]Campaign '{campaign_name}' not found.[/bold red]")
        raise typer.Exit(code=1)

    final_output_file = output_file if output_file else campaign_dir / "coverage.kml"


    assert campaign_name is not None # mypy needs this to understand campaign_name is not None here
    effective_campaign_name: str = campaign_name # Explicitly type hint for mypy

    try:
        scrape_index = ScrapeIndex(effective_campaign_name)
        if not scrape_index._index:
            console.print("[yellow]Scrape index is empty. No coverage to visualize.[/yellow]")
            return
    except FileNotFoundError:
        console.print(f"[bold red]Scrape index file not found for campaign '{str(campaign_name)}'.[/bold red]")
        full_path_str = f"{str(get_cocli_base_dir())}/indexes/{str(campaign_name)}/scraped_areas.csv"
        scraped_areas_csv_path = Path(full_path_str)
        console.print(f"[dim]Looked for: {scraped_areas_csv_path}[/dim]")
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

    joined_placemarks = "\n".join(kml_placemarks)
    kml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
    <Document>
        <name>Scrape Coverage for {campaign_name}</name>
{joined_placemarks}
    </Document>
</kml>'''

    try:
        with open(final_output_file, 'w') as f:
            f.write(kml_content)
        console.print(f"[bold green]Successfully generated KML file at: {final_output_file.absolute()}[/bold green]")
    except IOError as e:
        console.print(f"[bold red]Error writing to file {final_output_file}: {e}[/bold red]")
        raise typer.Exit(code=1)
