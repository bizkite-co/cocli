import typer
from pathlib import Path
from typing import Optional, List, Any
import asyncio
import logging

from ..enrichment.manager import EnrichmentManager
from ..core.config import get_companies_dir, get_people_dir
from ..models.companies.company import Company
from ..models.people.person import Person
from cocli.core.text_utils import slugify
from cocli.core.utils import create_person_files
from ..scrapers.generic_contact_scraper import GenericContactScraper

logger = logging.getLogger(__name__)
app = typer.Typer(no_args_is_help=True)


@app.command(name="run", no_args_is_help=True)
def run_enrichment(
    script_name: Optional[str] = typer.Argument(None, help="The name of the enrichment script to run."),
    company_name: Optional[str] = typer.Option(
        None, "--company", "-c", help="Specify a single company to enrich."
    ),
    all_companies: bool = typer.Option(
        False, "--all", "-a", help="Run the enrichment script on all companies."
    ),
    unenriched_only: bool = typer.Option(
        False, "--unenriched-only", "-u", help="Run the enrichment script only on companies that have not been enriched by this script yet."
    ),
    data_dir: Path = typer.Option(
        get_companies_dir(),
        "--data-dir",
        "-d",
        help="Directory containing company data. Defaults to the 'data/companies' directory.",
    ),
) -> None:
    """
    Run a specific enrichment script on one or all companies.
    """
    # Validate arguments
    if not script_name and (company_name or all_companies or unenriched_only):
        logger.error("Error: A script name must be provided when specifying companies to enrich.")
        raise typer.Exit(code=1)

    if not company_name and not all_companies and not unenriched_only:
        # This case is handled by no_args_is_help=True, which will show help.
        # If we reach here, it means no arguments were provided at all.
        return

    if (company_name and all_companies) or \
       (company_name and unenriched_only) or \
       (all_companies and unenriched_only):
        logger.error("Error: Cannot provide more than one of --company, --all, or --unenriched-only.")
        raise typer.Exit(code=1)

    manager = EnrichmentManager(data_dir)
    available_scripts = manager.get_available_script_names()

    if script_name and script_name not in available_scripts:
        logger.error(f"Error: Enrichment script '{script_name}' not found.")
        logger.info(f"Available scripts: {', '.join(available_scripts)}")
        raise typer.Exit(code=1)

    companies_to_enrich: List[str] = []
    if company_name:
        companies_to_enrich.append(company_name)
    elif all_companies:
        companies_to_enrich = [d.name for d in data_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]
    elif unenriched_only:
        assert script_name is not None
        companies_to_enrich = manager.get_unenriched_companies(script_name) # script_name is guaranteed not None here

    if not companies_to_enrich:
        logger.info("No companies found to enrich.")
        return

    logger.info(f"Running enrichment script '{script_name}' on {len(companies_to_enrich)} companies...")

    all_success = True
    for current_company_name in companies_to_enrich:
        logger.info(f"  Processing company: '{current_company_name}'...")
        assert script_name is not None
        success = manager.run_enrichment_script(current_company_name, script_name) # script_name is guaranteed not None here
        if not success:
            all_success = False
            logger.error(f"  Enrichment for '{current_company_name}' failed. Continuing with others.")

    if all_success:
        logger.info(f"Enrichment script '{script_name}' completed successfully for all selected companies.")
    else:
        logger.warning(f"Enrichment script '{script_name}' completed with some failures.")
        raise typer.Exit(code=1)


@app.command(name="list")
def list_scripts(
    data_dir: Path = typer.Option(
        get_companies_dir(),
        "--data-dir",
        "-d",
        help="Directory containing company data. Defaults to the 'data/companies' directory.",
    ),
) -> None:
    """
    List all available enrichment scripts.
    """
    manager = EnrichmentManager(data_dir)
    available_scripts = manager.get_available_script_names()
    if available_scripts:
        logger.info("Available Enrichment Scripts:")
        for script in available_scripts:
            logger.info(f"- {script}")
    else:
        logger.info("No enrichment scripts found.")

@app.command(name="contacts")
def scrape_contacts(
    company_name: str = typer.Argument(..., help="Name of the company to scrape contacts for."),
) -> None:
    """
    Scrape contact information from a company's website and add/update them in the CRM.
    """
    companies_dir = get_companies_dir()
    company_slug = slugify(company_name)
    selected_company_dir = companies_dir / company_slug

    if not selected_company_dir.exists():
        logger.error(f"Company '{company_name}' not found.")
        raise typer.Exit(code=1)

    company = Company.from_directory(selected_company_dir)
    if not company or not company.domain:
        logger.error(f"Could not load company data or company domain for '{company_name}'.")
        raise typer.Exit(code=1)

    assert company.domain is not None # Ensure domain is not None for mypy

    logger.info(f"Scraping contacts for {company.name} ({company.domain})...")
    
    scraper = GenericContactScraper()
    
    async def run_scraper() -> List[Any]:
        if company.domain is None:
            return [] # Or handle this case as appropriate, e.g., log a warning and skip
        contact_pages = await scraper.find_contact_pages(company.domain)
        all_extracted_contacts = []
        for page_url in contact_pages:
            extracted_contacts = await scraper.scrape_page_for_contacts(page_url)
            all_extracted_contacts.extend(extracted_contacts)
        return all_extracted_contacts

    extracted_contacts_data = asyncio.run(run_scraper())

    if not extracted_contacts_data:
        logger.info(f"No contacts found for {company.name} on {company.domain}.")
        return

    people_dir = get_people_dir()
    company_contacts_dir = selected_company_dir / "contacts"
    company_contacts_dir.mkdir(exist_ok=True)

    for contact_data in extracted_contacts_data:
        name = contact_data['name']
        email = contact_data['email']
        role = contact_data['role']

        if not name and not email:
            continue # Skip if no name and no email

        # Check if person already exists for this company
        person_exists = False
        existing_person_dir: Optional[Path] = None
        for contact_symlink in company_contacts_dir.iterdir():
            if contact_symlink.is_symlink():
                resolved_person_dir = contact_symlink.resolve()
                existing_person = Person.from_directory(resolved_person_dir)
                if existing_person:
                    # Match by name and email (if both exist)
                    if existing_person.name == name and existing_person.email == email:
                        person_exists = True
                        existing_person_dir = resolved_person_dir
                        break
                    # Match by name if email is missing in existing, and new email is present
                    elif existing_person.name == name and not existing_person.email and email:
                        person_exists = True
                        existing_person_dir = resolved_person_dir
                        break
                    # Match by email if name is missing in existing, and new name is present
                    elif existing_person.email == email and not existing_person.name and name:
                        person_exists = True
                        existing_person_dir = resolved_person_dir
                        break

        if person_exists and existing_person_dir:
            # Update existing person
            existing_person = Person.from_directory(existing_person_dir)
            if existing_person:
                updated = False
                if not existing_person.email and email:
                    existing_person.email = email
                    updated = True
                if not existing_person.role and role:
                    existing_person.role = role
                    updated = True
                
                if updated:
                    create_person_files(existing_person, existing_person_dir)
                    logger.info(f"  Updated existing contact: {existing_person.name} ({existing_person.email})")
                else:
                    logger.info(f"  Contact already exists and is up-to-date: {existing_person.name} ({existing_person.email})")
        else:
            # Create new person
            person_name_to_use = name if name else email.split('@')[0] # Use email prefix if name is empty
            new_person = Person(
                name=person_name_to_use,
                email=email if email else None,
                phone=None, # Scraper doesn't get phone
                role=role if role else None,
                company_name=company.name, # Link to current company
                slug=slugify(person_name_to_use) # Add slug here
            )
            person_slug = slugify(new_person.name)
            new_person_dir = people_dir / person_slug
            
            # Ensure unique directory name if slug already exists
            counter = 1
            original_new_person_dir = new_person_dir
            while new_person_dir.exists():
                new_person_dir = original_new_person_dir.parent / f"{original_new_person_dir.name}-{counter}"
                counter += 1

            create_person_files(new_person, new_person_dir)
            logger.info(f"  Added new contact: {new_person.name} ({new_person.email})")

    logger.info(f"Finished scraping and updating contacts for {company.name}.")
