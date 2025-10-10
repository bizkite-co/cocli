import logging
import typer
import datetime
import subprocess
import re
import webbrowser
import yaml
import os
from pathlib import Path
from typing import Optional, List, Any, Dict

from rich.console import Console
from ..core.utils import _getch, create_person_files
from .add_meeting import _add_meeting_logic
from ..models.person import Person
from fuzzywuzzy import process # type: ignore

from ..core.config import get_companies_dir, get_people_dir, get_campaign
from ..core.utils import slugify
from ..renderers.company_view import display_company_view
from ..models.company import Company
from ..core.exclusions import ExclusionManager
from ..core.website_cache import WebsiteCache
from ..models.website import Website

console = Console()
app = typer.Typer()

def _load_frontmatter(index_path: Path) -> Dict[str, Any]:
    frontmatter_data: Dict[str, Any] = {}
    if index_path.exists():
        content = index_path.read_text()
        if content.startswith("---") and "---" in content[3:]:
            parts = content.split("---", 2)
            frontmatter_str = parts[1]
            try:
                frontmatter_data = yaml.safe_load(frontmatter_str) or {}
            except yaml.YAMLError as e:
                console.print(f"Error parsing YAML frontmatter: {e}")
    return frontmatter_data

@app.command()
def view_company(
    company_name: str = typer.Argument(..., help="Name of the company to view.")
):
    """
    View details of a specific company.
    """
    _interactive_view_company(company_name)

def _interactive_view_company(company_name: str):
    logger = logging.getLogger(__name__)
    logger.debug(f"Starting _interactive_view_company for {company_name}")
    companies_dir = get_companies_dir()
    logging.info(f"companies_dir: {companies_dir}")
    company_slug = slugify(company_name)
    logging.info(f"company_slug: {company_slug}")
    selected_company_dir = companies_dir / company_slug
    logging.info(f"selected_company_dir: {selected_company_dir}")

    if not selected_company_dir.exists():
        company_names = [d.name for d in companies_dir.iterdir() if d.is_dir()]
        matches = process.extractOne(company_name, company_names)
        if matches and matches[1] >= 80:
            if typer.confirm(f"Company '{company_name}' not found. Do you want to view '{matches[0]}' instead?"):
                selected_company_dir = companies_dir / slugify(matches[0])
                company_name = matches[0] # Update company_name to the matched one
            else:
                logger.info("Operation cancelled.")
                raise typer.Exit()
        else:
            logger.error(f"Company '{company_name}' not found.")
            raise typer.Exit(code=1)

    logger.debug("Calling Company.from_directory")
    company = Company.from_directory(selected_company_dir)
    if not company:
        logger.error(f"Could not load company data from {selected_company_dir}")
        raise typer.Exit(code=1)
    assert company is not None # Assert that company is not None

    if not company.slug:
        company.slug = slugify(company.name)


    website_cache = WebsiteCache()
    website_data: Optional[Website] = None
    if company.domain:
        website_data = website_cache.get_by_url(company.domain)

    while True:
        assert company is not None # Ensure company is not None for mypy
        meeting_map = display_company_view(console, company, website_data)
        console.print("\n[bold yellow]Press 'a' to add meeting, 'c' to add contact, 't' to add tag, 'e' to edit _index.md, 'E' to add email, 'w' to open website, 'p' to call, 'm' to select meeting, 'X' to exclude, 'f' to go back to fuzzy finder, 'C' to edit contact, 'q' to quit.[/bold yellow]")
        char = _getch()

        index_path = selected_company_dir / "_index.md"
        frontmatter_data = _load_frontmatter(index_path)

        if char == 'f':
            from .fz import fz
            from ..core.config import get_context
            console.clear()
            fz(filter_override=get_context())
            break
        elif char == 'E':
            console.print("\n[bold green]Adding a new email...[/bold green]")
            email = typer.prompt("Enter email address")
            if email:
                from .add_email import add_email
                try:
                    add_email(company_name=company.name, email=email)
                    frontmatter_data = _load_frontmatter(index_path) # Reload data
                    console.print(f"[bold green]Email '{email}' added. Press any key to continue.[/bold green]")
                except Exception as e:
                    console.print(f"[bold red]Error adding email: {e}. Press any key to continue.[/bold red]")
            else:
                console.print("[bold yellow]No email entered. Press any key to continue.[/bold yellow]")
            _getch()
        elif char == 'X':
            console.print("\n[bold red]Excluding company...[/bold red]")
            campaign = get_campaign()
            if not campaign:
                console.print("[bold red]No active campaign set. Use 'cocli campaign set <campaign_name>' to set one. Press any key to continue.[/bold red]")
                _getch()
                continue

            reason = typer.prompt("Reason for exclusion")
            logger.debug(f"Calling from_directory with: {selected_company_dir}")
            company = Company.from_directory(selected_company_dir)
            if company is None: # Handle the case where company is None after re-loading
                console.print("[bold red]Error: Could not reload company data after exclusion. Press any key to continue.[/bold red]")
                _getch()
                continue
            assert company is not None # Assert that company is not None after re-loading

            if company.domain: # Now company is guaranteed not to be None
                exclusion_manager = ExclusionManager(campaign=campaign)
                exclusion_manager.add_exclusion(domain=company.domain, reason=reason)
                console.print(f"[bold red]Company {company.name} excluded from campaign '{campaign}'. Press any key to continue.[/bold red]")
        elif char == 'a':
            console.print("\n[bold green]Adding a new meeting...[/bold green]")
            meeting_date_str = typer.prompt("Enter meeting date (e.g., 'today', 'next Monday', '2025-12-25')")
            _add_meeting_logic(company_name=company.name, date_str=meeting_date_str)
            console.print("[bold green]Meeting added. Press any key to continue.[/bold green]")
            _getch() # Wait for a key press to clear the message
        elif char == 'e':
            console.print("\n[bold green]Opening _index.md in Vim...[/bold green]")
            try:
                subprocess.run(["vim", str(index_path)], check=True)
                frontmatter_data = _load_frontmatter(index_path)
            except Exception as e:
                console.print(f"[bold red]Error opening Vim: {e}[/bold red]")
            console.print("[bold green]_index.md closed. Press any key to continue.[/bold green]")
            _getch() # Wait for a key press to clear the message
        elif char == 'w':
            console.print("\n[bold green]Opening company website...[/bold green]")
            domain = frontmatter_data.get('domain')
            if domain:
                url = f"http://{domain}"
                try:
                    webbrowser.open(url)
                    console.print(f"[bold green]Opened {url} in browser. Press any key to continue.[/bold green]")
                except Exception as e:
                    console.print(f"[bold red]Error opening browser: {e}[/bold red]")
            else:
                console.print("[bold red]No domain found for this company. Press any key to continue.[/bold red]")
            _getch() # Wait for a key press to clear the message
        elif char == 'p':
            console.print("\n[bold green]Initiating phone call...[/bold green]")
            phone_number = frontmatter_data.get('phone_number')
            if phone_number:
                # Clean the phone number for the tel: URI
                cleaned_phone_number = re.sub(r'\D', '', phone_number)
                if not cleaned_phone_number.startswith('+1'):
                    cleaned_phone_number = '+1' + cleaned_phone_number # Assuming US numbers, adjust if needed

                google_voice_url = f"https://voice.google.com/u/0/calls?a=nc,%2B{cleaned_phone_number}"
                try:
                    webbrowser.open(google_voice_url)
                    console.print(f"[bold green]Initiated call to {phone_number}. Auto-creating meeting...[/bold green]")
                    _add_meeting_logic(company_name=company.name, date_str="today", title_str="Google Voice Call", phone_number_str=phone_number)
                    console.print("[bold green]Meeting for call added. Press any key to continue.[/bold green]")
                except Exception as e:
                    console.print(f"[bold red]Error initiating call: {e}. Press any key to continue.[/bold red]")
            else:
                console.print("[bold red]No phone number found for this company. Press any key to continue.[/bold red]")
            _getch() # Wait for a key press to clear the message
        elif char == 'm':
            console.print("\n[bold green]Select a meeting by number:[/bold green]")
            try:
                meeting_num_str = typer.prompt("Enter meeting number")
                meeting_num = int(meeting_num_str)
                selected_meeting_file = meeting_map.get(meeting_num)
                if selected_meeting_file:
                    console.print(f"\n[bold green]Opening meeting: {selected_meeting_file.name} in Vim...[/bold green]")
                    subprocess.run(["vim", str(selected_meeting_file)], check=True)
                    console.print("[bold green]Meeting closed. Press any key to continue.[/bold green]")
                else:
                    console.print(f"[bold red]Invalid meeting number: {meeting_num}. Press any key to continue.[/bold red]")
                _getch()
            except ValueError:
                console.print("[bold red]Invalid input. Please enter a number. Press any key to continue.[/bold red]")
                _getch()
            except Exception as e:
                console.print(f"[bold red]Error opening Vim: {e}. Press any key to continue.[/bold red]")
                _getch()
        elif char == 'c':
            console.print("\n[bold green]Add a new contact...[/bold green]")
            people_dir = get_people_dir()
            if not people_dir.exists():
                console.print("[bold red]People directory not found. Press any key to continue.[/bold red]")
                _getch()
                continue

            people_names = [d.name for d in people_dir.iterdir() if d.is_dir()]
            if not people_names:
                console.print("[bold red]No people found in the people directory. Press any key to continue.[/bold red]")
                _getch()
                continue

            fzf_input = "\n".join(people_names)
            try:
                fzf_result = subprocess.run(
                    ["fzf"],
                    input=fzf_input,
                    stdout=subprocess.PIPE,
                    text=True,
                    check=True
                )
                selected_person_name = fzf_result.stdout.strip()

                if selected_person_name:
                    contacts_dir = selected_company_dir / "contacts"
                    contacts_dir.mkdir(exist_ok=True)
                    person_path = people_dir / selected_person_name
                    contact_symlink = contacts_dir / selected_person_name

                    if contact_symlink.exists():
                        console.print(f"[bold yellow]Contact ''{selected_person_name}'' already exists. Press any key to continue.[/bold yellow]")
                    else:
                        os.symlink(person_path, contact_symlink)
                        console.print(f"[bold green]Contact ''{selected_person_name}'' added. Press any key to continue.[/bold green]")
                else:
                    console.print("[bold yellow]No person selected. Press any key to continue.[/bold yellow]")

            except subprocess.CalledProcessError:
                console.print("[bold yellow]Contact selection cancelled. Press any key to continue.[/bold yellow]")
            except Exception as e:
                console.print(f"[bold red]Error adding contact: {e}. Press any key to continue.[/bold red]")
            _getch()
        elif char == 'C':
            console.print("\n[bold green]Editing a contact...[/bold green]")
            contacts_dir = selected_company_dir / "contacts"
            if not contacts_dir.exists() or not any(contacts_dir.iterdir()):
                console.print("[bold red]No contacts found for this company. Press any key to continue.[/bold red]")
                _getch()
                continue

            contact_names = []
            contact_paths = {}
            for contact_symlink in contacts_dir.iterdir():
                if contact_symlink.is_symlink():
                    person_dir = contact_symlink.resolve()
                    person = Person.from_directory(person_dir)
                    if person:
                        contact_names.append(person.name)
                        contact_paths[person.name] = person_dir

            if not contact_names:
                console.print("[bold red]No valid contacts found for this company. Press any key to continue.[/bold red]")
                _getch()
                continue

            fzf_input = "\n".join(contact_names)
            try:
                fzf_result = subprocess.run(
                    ["fzf"],
                    input=fzf_input,
                    stdout=subprocess.PIPE,
                    text=True,
                    check=True
                )
                selected_person_name = fzf_result.stdout.strip()

                if selected_person_name:
                    person_dir_to_edit = contact_paths[selected_person_name]
                    person_to_edit = Person.from_directory(person_dir_to_edit)

                    if person_to_edit:
                        console.print(f"\n[bold green]Editing contact: {person_to_edit.name}[/bold green]")
                        new_name = typer.prompt(f"Enter new name (current: {person_to_edit.name})", default=person_to_edit.name)
                        new_email = typer.prompt(f"Enter new email (current: {person_to_edit.email or 'None'})", default=person_to_edit.email or "")
                        new_phone = typer.prompt(f"Enter new phone (current: {person_to_edit.phone or 'None'})", default=person_to_edit.phone or "")
                        new_role = typer.prompt(f"Enter new role (current: {person_to_edit.role or 'None'})", default=person_to_edit.role or "")

                        person_to_edit.name = new_name
                        person_to_edit.email = new_email if new_email else None
                        person_to_edit.phone = new_phone if new_phone else None
                        person_to_edit.role = new_role if new_role else None

                        # Save the updated person
                        create_person_files(person_to_edit, person_dir_to_edit)
                        console.print(f"[bold green]Contact '{person_to_edit.name}' updated. Press any key to continue.[/bold green]")
                    else:
                        console.print("[bold red]Error: Could not load selected contact for editing. Press any key to continue.[/bold red]")
                else:
                    console.print("[bold yellow]No contact selected for editing. Press any key to continue.[/bold yellow]")

            except subprocess.CalledProcessError:
                console.print("[bold yellow]Contact editing cancelled. Press any key to continue.[/bold yellow]")
            except Exception as e:
                console.print(f"[bold red]Error editing contact: {e}. Press any key to continue.[/bold red]")
            _getch()
        elif char == 't':
            console.print("\n[bold green]Add a new tag...[/bold green]")
            new_tag = typer.prompt("Enter tag to add")
            if new_tag:
                tags_path = selected_company_dir / "tags.lst"
                try:
                    with tags_path.open('a+') as f:
                        f.seek(0)
                        tags = f.read().splitlines()
                        if new_tag not in tags:
                            f.write(f"{new_tag}\n")
                            console.print(f"[bold green]Tag ''{new_tag}'' added. Press any key to continue.[/bold green]")
                        else:
                            console.print(f"[bold yellow]Tag ''{new_tag}'' already exists. Press any key to continue.[/bold yellow]")
                except Exception as e:
                    console.print(f"[bold red]Error adding tag: {e}. Press any key to continue.[/bold red]")
            else:
                console.print("[bold yellow]No tag entered. Press any key to continue.[/bold yellow]")
            _getch()
        elif char == 'q':
            console.print("[bold green]Exiting company context.[/bold green]")
            break
        else:
            console.print(f"[bold red]Invalid option: '{char}'. Press 'a', 'e', 'w', 'p', 'm', 'C', or 'q'.[/bold red]")
            _getch() # Wait for a key press to clear the message

@app.command()
def view_meetings(
    company_name: str = typer.Argument(..., help="Name of the company to view meetings for.")
):
    """
    View all meetings for a specific company.
    """
    companies_dir = get_companies_dir()
    company_slug = slugify(company_name)
    company_dir = companies_dir / company_slug
    meetings_dir = company_dir / "meetings"

    if not company_dir.exists():
        logger.error(f"Company '{company_name}' not found.")
        raise typer.Exit(code=1)

    if not meetings_dir.exists() or not any(meetings_dir.iterdir()):
        logger.info(f"No meetings found for '{company_name}'.")
        return

    logger.info(f"\n--- All Meetings for {company_name} ---")
    for meeting_file in sorted(meetings_dir.iterdir()):
        if meeting_file.is_file() and meeting_file.suffix == ".md":
            try:
                date_str = meeting_file.name.split("-")[0:3]
                meeting_date = datetime.datetime.strptime(
                    "-".join(date_str), "%Y-%m-%d"
                ).date()
                logger.info(f"- {meeting_date.isoformat()}: {meeting_file.name}")
            except ValueError:
                logger.warning(f"- Malformed meeting file: {meeting_file.name}")


@app.command()
def open_company_folder(
    company_name: str = typer.Argument(..., help="Name of the company to open folder for.")
):
    """
    Open the company's folder in nvim.
    """
    companies_dir = get_companies_dir()
    company_slug = slugify(company_name)
    company_dir = companies_dir / company_slug

    if not company_dir.exists():
        logger.error(f"Company '{company_name}' not found.")
        raise typer.Exit(code=1)

    try:
        subprocess.run(["nvim", str(company_dir)], check=True)
    except Exception as e:
        logger.error(f"Error opening folder in nvim: {e}")
        raise typer.Exit(code=1)
