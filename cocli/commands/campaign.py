from playwright.async_api import async_playwright
from ..core.importing import import_prospect
import typer
import toml
import csv
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging
import re
import pandas as pd
import httpx

from ..models.website import Website
from ..scrapers.google_maps import scrape_google_maps

from ..core.config import get_companies_dir, get_campaign_dir, get_cocli_base_dir, get_people_dir, get_all_campaign_dirs, get_editor_command, get_enrichment_service_url, get_campaign_scraped_data_dir
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
from cocli.core.text_utils import slugify
from cocli.core.utils import run_fzf
from ..core.queue.factory import get_queue_manager # New import
from ..models.queue import QueueMessage # New import
from ..core.enrichment import enrich_company_website # New import
from ..core.exceptions import NavigationError

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

@app.command(name="set")
def set_default_campaign(campaign_name: str = typer.Argument(..., help="The name of the campaign to set as the current context.")) -> None:
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
                
                console.print(f"[green]Imported contact:{person.name}[/green]") 

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

    prospects_csv_path = get_campaign_scraped_data_dir(campaign_name) / "prospects.csv"
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
            new_company = import_prospect(prospect_data, campaign=campaign_name)

            if new_company:
                console.print(f"[green]Imported new prospect:{new_company.name}[/green]") 
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
    existing_companies_map: Dict[str, str],
    overlap_threshold_percent: float, # Moved to a non-default position
    zoom_out_button_selector: str,
    panning_distance_miles: int,
    initial_zoom_out_level: int,
    omit_zoom_feature: bool,
    force: bool,
    ttl_days: int,
    debug: bool,
    console: Console,
    browser_width: int,
    browser_height: int,
    location_prospects_index: LocationProspectsIndex,
    target_locations: Optional[List[Dict[str, Any]]] = None,
    aws_profile_name: Optional[str] = None,
    campaign_company_slug: Optional[str] = None,
    use_cloud_queue: bool = False,
    max_proximity_miles: float = 0.0,
    navigation_timeout_ms: Optional[int] = None, # New parameter
) -> None:
    
    queue_manager = get_queue_manager(f"{campaign_name}_enrichment", use_cloud=use_cloud_queue)
    stop_event = asyncio.Event()
    emails_found_count = 0
    
    # Shared browser instance
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not headed,
            devtools=devtools,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--disable-gpu'
            ]
        )
        
        # --- Consumer Task ---
        async def consumer_task() -> None:
            nonlocal emails_found_count
            console.print("[bold blue]Starting Enrichment Consumer...[/bold blue]")
            
            enrichment_url = get_enrichment_service_url()
            use_cloud_enrichment = enrichment_url != "http://localhost:8000" # Rudimentary check, can be improved
            
            consumer_context = await browser.new_context() if not use_cloud_enrichment else None
            
            while not stop_event.is_set():
                messages = queue_manager.poll(batch_size=1) # Start with 1 for safety
                
                if not messages:
                    # If queue is empty and producer is done (we need a way to know producer is done... 
                    # for now, just sleep. If producer finishes, we might want to drain queue then stop)
                    await asyncio.sleep(1)
                    continue
                
                for msg in messages:
                    if stop_event.is_set(): 
                        break
                    
                    console.print(f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/][dim]Processing: {msg.domain}[/dim]")
                    website_data = None
                    
                    # Enrich
                    if use_cloud_enrichment:
                        async with httpx.AsyncClient() as client:
                            try:
                                response = await client.post(
                                    f"{enrichment_url}/enrich",
                                    json={
                                        "domain": msg.domain,
                                        "force": msg.force_refresh,
                                        "ttl_days": msg.ttl_days,
                                        "debug": debug,
                                        "campaign_name": msg.campaign_name,
                                        "aws_profile_name": msg.aws_profile_name or aws_profile_name,
                                        "company_slug": campaign_company_slug or msg.company_slug,
                                        "navigation_timeout_ms": navigation_timeout_ms # Pass new param
                                    },
                                    timeout=120.0
                                )
                                response.raise_for_status()
                                response_json = response.json()
                                if response_json:
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
                            except httpx.HTTPStatusError as e:
                                status = e.response.status_code
                                if status == 404:
                                    console.print(f"[yellow]Service returned 404 for {msg.domain}. Saving empty result.[/yellow]")
                                    # Save empty result logic below (shared)
                                    website_data = Website(url=f"http://{msg.domain}", company_name=msg.domain)
                                elif status == 500:
                                    error_details = e.response.text[:200] if e.response else "No details"
                                    console.print(f"[bold red]HTTP 500 for {msg.domain}. Error: {error_details}. Retrying.[/bold red]")
                                    queue_manager.nack(msg, is_http_500=True)
                                    continue
                                else:
                                    console.print(f"[bold red]HTTP {status} for {msg.domain}. Retrying.[/bold red]")
                                    queue_manager.nack(msg)
                                    continue
                            except Exception as e:
                                logger.error(f"Enrichment failed for {msg.domain}: {e}")
                                queue_manager.nack(msg)
                                continue
                    else:
                        # Local Enrichment
                        # We need a Company object. We can reconstruct basic info or load from disk.
                        # Loading from disk is safer as 'import_prospect' created it.
                        # But msg only has pointers.
                        # Let's just pass a dummy company with the domain to the scraper
                        dummy_company = Company(name=msg.domain, domain=msg.domain, slug=msg.company_slug)
                        try:
                            assert consumer_context is not None
                            website_data = await enrich_company_website(
                                browser=consumer_context, # Pass context!
                                company=dummy_company,
                                # campaign object? We might need to construct it or pass None if local doesn't strictly need it for logic
                                # Local scraper mainly needs domain.
                                force=msg.force_refresh,
                                ttl_days=msg.ttl_days,
                                debug=debug
                            )
                        except NavigationError as e:
                             console.print(f"[yellow]Navigation failed for {msg.domain}: {e}. Saving empty result.[/yellow]")
                             # Treat as 404 - Save empty result
                             website_data = Website(url=f"http://{msg.domain}", company_name=msg.domain)
                        except Exception as e:
                             logger.error(f"Local enrichment failed: {e}")
                             queue_manager.nack(msg)
                             continue

                    # Handle Result (Success or Handled Failure)
                    if website_data:
                        if website_data.email:
                            console.print(f"[green]Found email: {website_data.email}[/green]")
                            emails_found_count += 1
                        else:
                            console.print(f"[dim]No email for {msg.domain} (Saving result)[/dim]")

                        # Create Skeleton if needed (Robustness)
                        company_dir = get_companies_dir() / msg.company_slug
                        if not (company_dir / "_index.md").exists():
                            console.print(f"[yellow]Creating skeleton company for {msg.company_slug}[/yellow]")
                            company_dir.mkdir(parents=True, exist_ok=True)
                            with open(company_dir / "_index.md", "w") as f:
                                f.write("---")
                                yaml.dump({"name": msg.domain, "domain": msg.domain}, f)
                                f.write("---")
                        
                        # Save to disk (Critical!)
                        enrichment_dir = company_dir / "enrichments"
                        enrichment_dir.mkdir(parents=True, exist_ok=True)
                        with open(enrichment_dir / "website.md", "w") as f:
                            f.write("---")
                            yaml.dump(website_data.model_dump(exclude_none=True), f)
                            f.write("---")
                        
                        compiler = WebsiteCompiler()
                        compiler.compile(company_dir)
                        
                        console.print(f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/][bold green]Progress: {emails_found_count} / {goal_emails} emails found.[/bold green]")
                        
                        if emails_found_count >= goal_emails:
                            console.print("[bold magenta]Goal Met! Stopping.[/bold magenta]")
                            stop_event.set()
                        
                        queue_manager.ack(msg)
                    else:
                        # Should not happen if 404 handled above, but just in case
                        console.print(f"[dim]No result data for {msg.domain}[/dim]")
                        queue_manager.ack(msg) # Ack to avoid loop if no exception but no data

        # --- Producer Task ---
        async def producer_task(existing_companies_map: Dict[str, str]) -> None:
            console.print("[bold blue]Starting Scraper Producer...[/bold blue]")
            
            # Initialize location data
            location_data = []
            
            if target_locations:
                # We rely on max_proximity_miles to constrain the search area around each target
                for loc in target_locations:
                    current_prospects = location_prospects_index.get_prospect_count(loc["name"])
                    location_data.append({
                        "name": loc["name"],
                        "prospect_count": current_prospects,
                        "latitude": loc.get("lat"),
                        "longitude": loc.get("lon"),
                        "saturation_score": loc.get("saturation_score", 0.0)
                    })
            else:
                for loc_name in locations:
                    current_prospects = location_prospects_index.get_prospect_count(loc_name)
                    location_data.append({
                        "name": loc_name, 
                        "prospect_count": current_prospects,
                        "saturation_score": 100000.0
                    })
            
            location_df = pd.DataFrame(location_data)

            prospects_csv_path = get_campaign_scraped_data_dir(campaign_name) / "prospects.csv"
            # prospects_csv_path.parent.mkdir(parents=True, exist_ok=True) # Handled by getter
            write_header = not prospects_csv_path.exists()
            
            with open(prospects_csv_path, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=GoogleMapsData.model_fields.keys())
                if write_header:
                    writer.writeheader()

                while not stop_event.is_set():
                    # Sort locations by saturation_score (primary) and prospect_count (secondary)
                    # We want least saturated first.
                    location_df = location_df.sort_values(by=["saturation_score", "prospect_count"], ascending=[True, True]).reset_index(drop=True)
                    
                    # Filter to candidates with the minimum saturation_score to ensure round-robin among equally unsaturated
                    if not location_df.empty:
                        min_saturation = location_df["saturation_score"].min()
                        # Use a small epsilon for float comparison if needed, but direct comparison is usually fine for sorted df head
                        candidates = location_df[location_df["saturation_score"] <= min_saturation + 0.01]
                    else:
                        candidates = location_df
                    
                    # Pick random 1 from the candidates
                    if len(candidates) > 0:
                        selected_locations = candidates.sample(n=1)
                    else:
                        # Fallback (shouldn't happen if list not empty)
                        selected_locations = location_df.head(1)
                    
                    for _, loc_row in selected_locations.iterrows():
                        if stop_event.is_set(): 
                            break
                        
                        location = str(loc_row["name"])
                        
                        logger.info(f"[bold yellow]Scraping target:[/bold yellow] {location}")
                        console.print(f"[bold yellow]Scraping target:[/bold yellow] {location}")

                        location_param = {"city": location}
                        if "latitude" in loc_row and pd.notnull(loc_row["latitude"]):
                             location_param["latitude"] = str(loc_row["latitude"])
                             location_param["longitude"] = str(loc_row["longitude"])
                        
                        # Scrape
                        prospect_generator = scrape_google_maps(
                            browser=browser, # Use main browser instance (new page per search)
                            location_param=location_param,
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
                            max_proximity_miles=max_proximity_miles,
                            overlap_threshold_percent=overlap_threshold_percent,
                        )
                        
                        async for prospect_data in prospect_generator:
                            if stop_event.is_set(): 
                                break
                            
                            # Write CSV
                            writer.writerow(prospect_data.model_dump())
                            
                            # Handle Company Lookup/Import
                            company: Optional[Company] = None
                            domain = prospect_data.Domain
                            
                            if domain and domain in existing_companies_map:
                                slug = existing_companies_map[domain]
                                company = Company.get(slug)
                            else:
                                # Import Local

                                company = import_prospect(prospect_data, campaign=campaign_name)
                                if company and company.domain:
                                    existing_companies_map[company.domain] = company.slug
                            
                            if company and company.domain:
                                location_prospects_index.update_prospect_count(location, 1)
                                location_df.loc[location_df["name"] == location, "prospect_count"] += 1
                                
                                # Decide whether to queue
                                should_queue = False
                                logger.debug(f"DEBUGGING QUEUE: Company {company.name} (Domain: {company.domain}, Slug: {company.slug}). Has email: {bool(company.email)}. Force mode: {force}")

                                if force:
                                    should_queue = True
                                    logger.debug(f"Queuing {company.domain}: --force is True.")
                                elif company.email: # Check if company already has an email
                                    logger.debug(f"Skipping queue for {company.domain}: Company already has email.")
                                else:
                                    # If no email, we queue it to try and find one
                                    should_queue = True
                                    logger.debug(f"Queuing {company.domain}: No email found yet.")
                                
                                if should_queue:
                                    # Push to Queue
                                    msg = QueueMessage(
                                        domain=company.domain,
                                        company_slug=company.slug,
                                        campaign_name=campaign_name,
                                        force_refresh=force,
                                        ttl_days=ttl_days,
                                        ack_token=None,
                                    )
                                    queue_manager.push(msg)
                                    console.print(f"[cyan]Queued: {company.name} (Domain: {company.domain})[/cyan]")
                                    logger.debug(f"Pushed to queue: Domain={company.domain}, Slug={company.slug}")
                                else:
                                    logger.debug(f"NOT QUEUED: {company.domain} based on logic. Has email: {bool(company.email)}. Force mode: {force}")
                            
                            # Yield control to let consumer run
                            await asyncio.sleep(0.01)

        # Run both
        await asyncio.gather(producer_task(existing_companies_map), consumer_task())
        console.print("[bold green]Pipeline Finished.[/bold green]")


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

    browser_height: int = typer.Option(2000, help="The height of the browser viewport."),

    cloud_queue: bool = typer.Option(False, "--cloud-queue", help="Use the cloud SQS queue instead of local file queue."),
    proximity_miles: float = typer.Option(10.0, "--proximity", help="Max radius in miles to scrape around each target location."),
    opt_panning_distance_miles: Optional[int] = typer.Option(None, "--panning-distance", help="Distance in miles to pan in each step of the spiral search. Overrides config.toml."),
    opt_initial_zoom_out_level: Optional[int] = typer.Option(None, "--initial-zoom", help="Initial zoom-out level at the start of scraping. Overrides config.toml."),
    opt_zoom_out_button_selector: Optional[str] = typer.Option(None, "--zoom-selector", help="CSS selector for the zoom out button. Overrides config.toml."),
    opt_omit_zoom_feature: Optional[bool] = typer.Option(None, "--omit-zoom", help="Omit the initial zoom-out feature. Overrides config.toml."),
    opt_allowed_overlap_percentage: Optional[float] = typer.Option(None, "--overlap-percentage", help="Minimum overlap percentage to consider an area already scraped or wilderness. Overrides config.toml."),
    navigation_timeout_ms: Optional[int] = typer.Option(None, "--navigation-timeout", help="Timeout in milliseconds for Playwright navigation in the enrichment service. Overrides default."),
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
            f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [yellow]Note: The 'achieve-goal' pipeline runs sequentially when a specific email goal is set, processing one prospect at a time through Google Maps scraping and website enrichment.[/yellow]"        )  # --- Load Campaign Config ---

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
    
    # Use command-line options if provided, otherwise fall back to config
    zoom_out_button_selector = opt_zoom_out_button_selector if opt_zoom_out_button_selector is not None else prospecting_config.get("zoom-out-button-selector", "div#zoomOutButton")
    panning_distance_miles = opt_panning_distance_miles if opt_panning_distance_miles is not None else prospecting_config.get("panning-distance-miles", 8)
    initial_zoom_out_level = opt_initial_zoom_out_level if opt_initial_zoom_out_level is not None else prospecting_config.get("initial-zoom-out-level", 3)
    omit_zoom_feature = opt_omit_zoom_feature if opt_omit_zoom_feature is not None else prospecting_config.get("omit-zoom-feature", False)
    allowed_overlap_percentage = opt_allowed_overlap_percentage if opt_allowed_overlap_percentage is not None else prospecting_config.get("allowed-overlap-percentage", 30.0)
    
    target_locations_csv = prospecting_config.get("target-locations-csv")

    target_locations = None
    if target_locations_csv:
        csv_path = Path(target_locations_csv)
        if not csv_path.is_absolute():
            csv_path = campaign_dir / csv_path
        
        if csv_path.exists():
            target_locations = []
            try:
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if "name" in row and "lat" in row and "lon" in row:
                            target_locations.append({
                                "name": row["name"],
                                "lat": float(row["lat"]),
                                "lon": float(row["lon"]),
                                "saturation_score": float(row.get("saturation_score", 0.0))
                            })
                console.print(f"[green]Loaded {len(target_locations)} target locations from {csv_path.name}[/green]")
            except Exception as e:
                logger.error(f"Error reading target locations CSV: {e}")
        else:
            logger.warning(f"Target locations CSV configured but not found at {csv_path}")

    if (not locations and not target_locations) or not search_phrases:
        logger.error("No locations (or target-locations-csv) or queries found in the prospecting configuration.")

        raise typer.Exit(code=1)  # --- Setup ---

    setup_file_logging(f"{campaign_name}-achieve-goal", file_level=logging.DEBUG, disable_console=True)

    console.print(
        f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [dim]Building map of existing companies...[/dim]"
    )

    existing_companies_map = {c.domain: c.slug for c in Company.get_all() if c.domain and c.slug}

    location_prospects_index = LocationProspectsIndex(campaign_name=campaign_name)
    
    aws_profile_name = config.get("aws", {}).get("profile")
    campaign_company_slug = config.get("campaign", {}).get("company-slug")

    # --- Main Pipeline Loop ---
    asyncio.run(
        pipeline(
            locations=locations,
            target_locations=target_locations,
            aws_profile_name=aws_profile_name,
            campaign_company_slug=campaign_company_slug,
            search_phrases=search_phrases,
            goal_emails=goal_emails,
            headed=headed,
            devtools=devtools,
            campaign_name=campaign_name,
            overlap_threshold_percent=allowed_overlap_percentage,
            zoom_out_button_selector=zoom_out_button_selector,
            panning_distance_miles=panning_distance_miles,
            initial_zoom_out_level=initial_zoom_out_level,
            omit_zoom_feature=omit_zoom_feature,
            force=force,
            ttl_days=ttl_days,
            debug=debug,
            existing_companies_map=existing_companies_map,
            console=console,
            browser_width=browser_width,
            browser_height=browser_height,
            location_prospects_index=location_prospects_index,
            use_cloud_queue=cloud_queue,
            max_proximity_miles=proximity_miles,
            navigation_timeout_ms=navigation_timeout_ms,
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

    # Load search phrases from campaign config to find relevant indexes
    config_path = campaign_dir / "config.toml"
    if not config_path.exists():
        console.print(f"[bold red]Configuration file not found for campaign '{effective_campaign_name}'.[/bold red]")
        raise typer.Exit(code=1)
    
    with open(config_path, "r") as f:
        config = toml.load(f)
    
    search_phrases = config.get("prospecting", {}).get("queries", [])
    if not search_phrases:
        console.print("[yellow]No search phrases found in campaign configuration.[/yellow]")
        return

    scrape_index = ScrapeIndex()
    scraped_areas = scrape_index.get_all_areas_for_phrases(search_phrases)
    wilderness_areas = scrape_index._load_wilderness_areas() # Load wilderness areas

    all_areas = scraped_areas + wilderness_areas
    
    if not all_areas:
        console.print("[yellow]No scraped or wilderness areas found for the campaign's search phrases.[/yellow]")
        return

    # Assign colors to phrases and wilderness
    phrases = sorted(list({area.phrase for area in scraped_areas}))
    colors = ["ff0000ff", "ff00ff00", "ffff0000", "ff00ffff", "ffff00ff", "ffffff00"] # Red, Green, Blue, Cyan, Magenta, Yellow
    phrase_colors = {phrase: colors[i % len(colors)] for i, phrase in enumerate(phrases)}
    phrase_colors["wilderness"] = "ff808080" # Grey for wilderness areas

    kml_placemarks = []
    for area in all_areas:
        coordinates = (
            f"{area.lon_min},{area.lat_min},0 "
            f"{area.lon_max},{area.lat_min},0 "
            f"{area.lon_max},{area.lat_max},0 "
            f"{area.lon_min},{area.lat_max},0 "
            f"{area.lon_min},{area.lat_min},0"
        )
        placemark = f'''        <Placemark>
            <name>{area.phrase}</name>
            <description><![CDATA[
                <b>Scrape Date:</b> {area.scrape_date.strftime('%Y-%m-%d %H:%M:%S')}<br/>
                <b>Lat Miles:</b> {area.lat_miles:.3f}<br/>
                <b>Lon Miles:</b> {area.lon_miles:.3f}<br/>
                <b>Items Found:</b> {area.items_found}<br/>
                <b>Bounds:</b><br/>
                &nbsp;&nbsp;Lat: {area.lat_min:.5f} to {area.lat_max:.5f}<br/>
                &nbsp;&nbsp;Lon: {area.lon_min:.5f} to {area.lon_max:.5f}
            ]]></description>
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
