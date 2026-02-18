import yaml
import logging
import typer
from typing import Any, Dict
from pathlib import Path
import subprocess
import webbrowser
import re
import os
import shutil
import sys
import datetime

from rich.console import Console


from cocli.core.text_utils import slugify
from cocli.core.utils import _getch, run_fzf, create_person_files
from cocli.core.paths import paths
from ..core.config import get_campaign, get_editor_command, get_enrichment_service_url
from ..models.company import Company
from ..models.person import Person
from ..models.note import Note


from ..models.website import Website
from ..renderers.company_view import display_company_view
from ..core.exclusions import ExclusionManager
from ..commands.add_meeting import _add_meeting_logic
from ..core.website_domain_csv_manager import WebsiteDomainCsvManager
from ..application.company_service import get_company_details_for_view # New Import
import httpx
from ..compilers.website_compiler import WebsiteCompiler

logger = logging.getLogger(__name__)
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
    company_slug: str = typer.Argument(..., help="Slug of the company to view.")
) -> None:
    """
    View details of a specific company.
    """
    _interactive_view_company(company_slug)

def _interactive_view_company(company_slug: str) -> None:
    logger = logging.getLogger(__name__)
    logger.debug(f"Starting _interactive_view_company for slug: {company_slug}")

    while True:
        company_data = get_company_details_for_view(company_slug)
        if not company_data:
            logger.error(f"Company data for slug '{company_slug}' not found.")
            raise typer.Exit(code=1)

        company = Company.model_validate(company_data["company"])
        display_company_view(console, company_data)
        console.print("\n[bold yellow]Press 'a' to add meeting, 'c' for contact menu, 't' to add tag, 'T' to remove tag, 'e' to edit _index.md, 'E' to add email, 'w' to open website, 'p' to call, 'm' to select meeting, 'X' to exclude, 'f' to go back to fuzzy finder, 'r' to re-enrich, 'n' to add note, 'N' to edit note, 'q' to quit.[/bold yellow]")
        char = _getch()

        selected_company_dir = paths.companies.path / company_slug
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
            # Reload company data to ensure it's up-to-date after potential external changes
            reloaded_company = Company.from_directory(selected_company_dir)
            if reloaded_company is None:
                console.print("[bold red]Error: Could not reload company data after exclusion. Press any key to continue.[/bold red]")
                _getch()
                continue
            company = reloaded_company # Update the company object in the current scope

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
            console.print("\n[bold green]Opening _index.md in NVim...[/bold green]")
            try:
                subprocess.run(["nvim", str(index_path)], check=True)
                frontmatter_data = _load_frontmatter(index_path)
            except Exception as e:
                console.print(f"[bold red]Error opening NVim: {e}[/bold red]")
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
            meetings_data = company_data["meetings"]
            if meetings_data:
                # Reconstruct meeting_map from meetings_data for selection
                meeting_map = {i + 1: Path(m["file_path"]) for i, m in enumerate(meetings_data)}
                
                console.print("\n[bold blue]Available Meetings:[/bold blue]")
                for i, m in enumerate(meetings_data, 1):
                    # Rewritten f-string to avoid nested quotes issue
                    console.print(f"  [bold green]{i}.[/bold green] {m['title']} ({datetime.datetime.fromisoformat(m['datetime_utc']).strftime('%Y-%m-%d %H:%M')})")

                try:
                    meeting_num_str = typer.prompt("Enter meeting number")
                    meeting_num = int(meeting_num_str)
                    selected_meeting_file = meeting_map.get(meeting_num)
                    if selected_meeting_file:
                        console.print(f"\n[bold green]Opening meeting: {selected_meeting_file.name} in NVim...[/bold green]")
                        subprocess.run(["nvim", str(selected_meeting_file)], check=True)
                        console.print("[bold green]Meeting closed. Press any key to continue.[/bold green]")
                    else:
                        console.print(f"[bold red]Invalid meeting number: {meeting_num}. Press any key to continue.[/bold red]")
                    _getch()
                except ValueError:
                    console.print("[bold red]Invalid input. Please enter a number. Press any key to continue.[/bold red]")
                    _getch()
                except Exception as e:
                    console.print(f"[bold red]Error opening NVim: {e}. Press any key to continue.[/bold red]")
                    _getch()
            else:
                console.print("[bold yellow]No meetings found for this company. Press any key to continue.[/bold yellow]")
                _getch()
        elif char == 'c':
            while True:
                console.clear()
                display_company_view(console, company_data) # Re-display company view
                console.print("\n[bold yellow]Contact Menu:[/bold yellow]")
                console.print("  [bold green]1.[/bold green] Add New Contact")
                console.print("  [bold green]2.[/bold green] Add Existing Contact")
                console.print("  [bold green]3.[/bold green] Edit Contact")
                console.print("  [bold green]4.[/bold green] Delete Contact")
                console.print("  [bold red]q.[/bold red] Back to Company View")
                contact_choice = _getch()

                if contact_choice == '1':
                    console.print("\n[bold green]Adding a new contact...[/bold green]")
                    contact_name = typer.prompt("Enter contact name")
                    if not contact_name:
                        console.print("[bold yellow]Contact name cannot be empty. Press any key to continue.[/bold yellow]")
                        _getch()
                        continue

                    contact_email = typer.prompt("Enter contact email (optional)", default="")
                    contact_phone = typer.prompt("Enter contact phone (optional, e.g., +1-555-123-4567)", default="")
                    contact_role = typer.prompt("Enter contact role (optional)", default="")

                    new_person = Person(name=contact_name, email=contact_email if contact_email else None, phone=contact_phone if contact_phone else None, role=contact_role if contact_role else None, slug=slugify(contact_name)) # Add slug here
                    
                    people_dir = paths.people.path
                    person_dir = people_dir / slugify(new_person.name)
                    create_person_files(new_person, person_dir)

                    contacts_dir = selected_company_dir / "contacts"
                    contacts_dir.mkdir(exist_ok=True)
                    contact_symlink = contacts_dir / person_dir.name

                    if contact_symlink.exists():
                        console.print(f"[bold yellow]Contact ''{new_person.name}'' already exists for this company. Press any key to continue.[/bold yellow]")
                    else:
                        os.symlink(person_dir, contact_symlink, target_is_directory=True)
                        console.print(f"[bold green]New contact ''{new_person.name}'' added. Press any key to continue.[/bold green]")
                    _getch()
                elif contact_choice == '2':
                    console.print("\n[bold green]Adding an existing contact...[/bold green]")
                    people_dir = paths.people.path
                    if not people_dir.exists():
                        console.print("[bold red]People directory not found. Press any key to continue.[/bold red]")
                        _getch()
                        continue

                    people_names = []
                    person_paths = {}
                    for person_dir_item in people_dir.iterdir():
                        if person_dir_item.is_dir():
                            person = Person.from_directory(person_dir_item)
                            if person:
                                people_names.append(person.name)
                                person_paths[person.name] = person_dir_item

                    if not people_names:
                        console.print("[bold red]No people found in the people directory. Press any key to continue.[/bold red]")
                        _getch()
                        continue

                    fzf_input = "\n".join(people_names)
                    try:
                        selected_person_name = run_fzf(fzf_input)

                        if selected_person_name:
                            contacts_dir = selected_company_dir / "contacts"
                            contacts_dir.mkdir(exist_ok=True)
                            person_path = person_paths[selected_person_name]
                            contact_symlink = contacts_dir / person_path.name

                            if contact_symlink.exists():
                                console.print(f"[bold yellow]Contact ''{selected_person_name}'' already exists for this company. Press any key to continue.[/bold yellow]")
                            else:
                                os.symlink(person_path, contact_symlink, target_is_directory=True)
                                console.print(f"[bold green]Contact ''{selected_person_name}'' added. Press any key to continue.[/bold green]")
                        else:
                            console.print("[bold yellow]No contact selected. Press any key to continue.[/bold yellow]")

                    except subprocess.CalledProcessError:
                        console.print("[bold yellow]Contact selection cancelled. Press any key to continue.[/bold yellow]")
                    except Exception as e:
                        console.print(f"[bold red]Error adding contact: {e}. Press any key to continue.[/bold red]")
                    _getch()
                elif contact_choice == '3':
                    console.print("\n[bold green]Editing a contact...[/bold green]")
                    contacts_dir = selected_company_dir / "contacts"
                    if not contacts_dir.exists() or not any(contacts_dir.iterdir()):
                        console.print("[bold red]No contacts found for this company. Press any key to continue.[/bold red]")
                        _getch()
                        continue

                    contact_names = []
                    contact_person_dirs = {}
                    for contact_symlink in contacts_dir.iterdir():
                        if contact_symlink.is_symlink():
                            person_dir = contact_symlink.resolve()
                            person = Person.from_directory(person_dir)
                            if person:
                                contact_names.append(person.name)
                                contact_person_dirs[person.name] = person_dir

                    if not contact_names:
                        console.print("[bold red]No valid contacts found for this company. Press any key to continue.[/bold red]")
                        _getch()
                        continue

                    fzf_input = "\n".join(contact_names)
                    try:
                        selected_person_name = run_fzf(fzf_input)

                        if selected_person_name:
                            person_dir_to_edit = contact_person_dirs[selected_person_name]
                            person_index_path = person_dir_to_edit / "_index.md"
                            editor_command = get_editor_command()
                            if editor_command:
                                try:
                                    subprocess.run([editor_command, str(person_index_path)], check=True)
                                    console.print("[bold green]Contact edited. Press any key to continue.[/bold green]")
                                except Exception as e:
                                    console.print(f"[bold red]Error opening editor: {e}. Press any key to continue.[/bold red]")
                            else:
                                console.print("[bold red]No editor configured. Please configure an editor in your cocli_config.toml. Press any key to continue.[/bold red]")
                        else:
                            console.print("[bold yellow]No contact selected for editing. Press any key to continue.[/bold yellow]")

                    except subprocess.CalledProcessError:
                        console.print("[bold yellow]Contact editing cancelled. Press any key to continue.[/bold yellow]")
                    except Exception as e:
                        console.print(f"[bold red]Error editing contact: {e}. Press any key to continue.[/bold red]")
                    _getch()
                elif contact_choice == '4':
                    console.print("\n[bold green]Deleting a contact...[/bold green]")
                    contacts_dir = selected_company_dir / "contacts"
                    if not contacts_dir.exists() or not any(contacts_dir.iterdir()):
                        console.print("[bold red]No contacts found for this company. Press any key to continue.[/bold red]")
                        _getch()
                        continue

                    contact_names = []
                    contact_symlinks = {}
                    for contact_symlink in contacts_dir.iterdir():
                        if contact_symlink.is_symlink():
                            person = Person.from_directory(contact_symlink.resolve())
                            if person:
                                contact_names.append(person.name)
                                contact_symlinks[person.name] = contact_symlink

                    if not contact_names:
                        console.print("[bold red]No valid contacts found for this company. Press any key to continue.[/bold red]")
                        _getch()
                        continue

                    fzf_input = "\n".join(contact_names)
                    try:
                        selected_person_name = run_fzf(fzf_input)

                        if selected_person_name:
                            symlink_to_delete = contact_symlinks[selected_person_name]
                            person_dir_to_delete = symlink_to_delete.resolve()

                            if typer.confirm(f"Are you sure you want to remove contact '{selected_person_name}' from this company?"):
                                symlink_to_delete.unlink() # Remove the symlink
                                console.print(f"[bold green]Contact '{selected_person_name}' removed from company. Press any key to continue.[/bold green]")

                                if typer.confirm(f"Do you also want to permanently delete the person file for '{selected_person_name}' from the system?"):
                                    # Delete the person directory and its contents
                                    shutil.rmtree(person_dir_to_delete)
                                    console.print(f"[bold green]Person file for '{selected_person_name}' permanently deleted.[/bold green]")
                                else:
                                    console.print(f"[bold yellow]Person file for '{selected_person_name}' retained.[/bold yellow]")
                            else:
                                console.print("[bold yellow]Contact removal cancelled. Press any key to continue.[/bold yellow]")
                        else:
                            console.print("[bold yellow]No contact selected for deletion. Press any key to continue.[/bold yellow]")

                    except subprocess.CalledProcessError:
                        console.print("[bold yellow]Contact deletion cancelled. Press any key to continue.[/bold yellow]")
                    except Exception as e:
                        console.print(f"[bold red]Error deleting contact: {e}. Press any key to continue.[/bold red]")
                    _getch()
                elif contact_choice == 'q':
                    break
                else:
                    console.print(f"[bold red]Invalid option: '{contact_choice}'. Press any key to continue.[/bold red]")
                    _getch()
            console.clear() # Clear menu before returning to main view


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
        elif char == 'T':
            console.print("\n[bold green]Remove a tag...[/bold green]")
            tag_to_remove = typer.prompt("Enter tag to remove")
            if tag_to_remove:
                tags_path = selected_company_dir / "tags.lst"
                if tags_path.exists():
                    try:
                        with tags_path.open('r') as f:
                            tags = f.read().splitlines()

                        if tag_to_remove in tags:
                            tags.remove(tag_to_remove)
                            with tags_path.open('w') as f:
                                f.write("\n".join(tags) + "\n")
                            console.print(f"[bold green]Tag ''{tag_to_remove}'' removed. Press any key to continue.[/bold green]")
                        else:
                            console.print(f"[bold yellow]Tag ''{tag_to_remove}'' not found. Press any key to continue.[/bold yellow]")
                    except Exception as e:
                        console.print(f"[bold red]Error removing tag: {e}. Press any key to continue.[/bold red]")
                else:
                    console.print("[bold yellow]No tags file found. Press any key to continue.[/bold yellow]")
            else:
                console.print("[bold yellow]No tag entered. Press any key to continue.[/bold yellow]")
            _getch()
        elif char == 'r':
            console.print("\n[bold green]Re-enriching company...[/bold green]")
            contacts_dir = selected_company_dir / "contacts"
            potential_domains = []
            if contacts_dir.exists():
                domain_manager = WebsiteDomainCsvManager()
                for contact_symlink in contacts_dir.iterdir():
                    if contact_symlink.is_symlink():
                        person_dir = contact_symlink.resolve()
                        person = Person.from_directory(person_dir)
                        if person and person.email:
                            domain = person.email.split('@')[1]
                            domain_info = domain_manager.get_by_domain(domain)
                            if not (domain_info and domain_info.is_email_provider):
                                if domain not in potential_domains:
                                    potential_domains.append(domain)

            if not potential_domains:
                console.print("No new potential domains found from contacts. Press any key to continue.")
                _getch()
                continue

            new_domain = None
            if len(potential_domains) == 1:
                if potential_domains[0] != company.domain:
                    if typer.confirm(f"Found potential domain '{potential_domains[0]}'. Update company domain and enrich?"):
                        new_domain = potential_domains[0]
                else:
                    console.print(f"Potential domain '{potential_domains[0]}' is already the company domain. Re-enriching. Press any key to continue.")
                    new_domain = potential_domains[0]
                    _getch()
            else:
                console.print("Multiple potential domains found. Please choose one:")
                for i, domain in enumerate(potential_domains, 1):
                    console.print(f"{i}. {domain}")
                choice_str = typer.prompt("Enter number of domain to set (or 's' to skip)")
                if choice_str.lower() == 's':
                    continue
                try:
                    choice = int(choice_str) - 1
                    if 0 <= choice < len(potential_domains):
                        new_domain = potential_domains[choice]
                    else:
                        console.print("Invalid choice. Press any key to continue.")
                        _getch()
                        continue
                except ValueError:
                    console.print("Invalid input. Press any key to continue.")
                    _getch()
                    continue

            if new_domain:
                # Update domain in _index.md
                index_path = selected_company_dir / "_index.md"
                content = index_path.read_text()
                frontmatter_str, markdown_content = content.split("---", 2)[1:]
                frontmatter_data = yaml.safe_load(frontmatter_str) or {}
                frontmatter_data['domain'] = new_domain
                new_frontmatter_str = yaml.dump(frontmatter_data)
                new_content = f"---\n{new_frontmatter_str}---\n{markdown_content}"
                index_path.write_text(new_content)
                company.domain = new_domain # Update the in-memory company object
                console.print(f"Company domain updated to '{new_domain}'. Triggering enrichment...")

                # Trigger enrichment service
                website_data = None
                enrichment_service_url = get_enrichment_service_url()
                try:
                    with httpx.Client() as client:
                        response = client.post(
                            f"{enrichment_service_url}/enrich",
                            json={
                                "domain": new_domain,
                                "force": True, # Force re-enrichment
                            },
                            timeout=120.0,
                        )
                        response.raise_for_status()
                        response_json = response.json()
                        if response_json:
                            website_data = Website(**response_json)
                except httpx.RequestError as e:
                    console.print(f"[bold red]HTTP request to enrichment service failed: {e}[/bold red]")
                except Exception as e:
                    console.print(f"[bold red]Error processing enrichment response: {e}[/bold red]")

                if website_data:
                    company.last_enriched = datetime.datetime.now(datetime.UTC) # Set last_enriched timestamp
                    console.print(f"[bold green]Enrichment successful. New email: {website_data.email}[/bold green]")
                    # Save enrichment data and compile
                    enrichment_dir = selected_company_dir / "enrichments"
                    website_md_path = enrichment_dir / "website.md"
                    website_data.associated_company_folder = selected_company_dir.name
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
                    compiler.compile(selected_company_dir)
                    console.print("[bold green]Enrichment data saved and compiled. Press any key to continue.[/bold green]")
                else:
                    console.print("[bold yellow]Enrichment did not return data. Press any key to continue.[/bold yellow]")
            else:
                console.print("No domain updated. Press any key to continue.")
            _getch()
        elif char == 'n':
            console.print("\n[bold green]Adding a new note...[/bold green]")
            note_title = typer.prompt("Enter note title")
            if not note_title:
                console.print("[bold yellow]Note title cannot be empty. Press any key to continue.[/bold yellow]")
                _getch()
                continue

            console.print("Enter note content (Press Ctrl+D to save, Ctrl+C to cancel):")
            # Read multi-line input until EOF (Ctrl+D)
            note_content_lines = []
            while True:
                try:
                    line = sys.stdin.readline()
                    if not line:
                        break
                    note_content_lines.append(line)
                except KeyboardInterrupt:
                    console.print("[bold yellow]Note creation cancelled. Press any key to continue.[/bold yellow]")
                    _getch()
                    break
            note_content = "".join(note_content_lines).strip()

            if not note_content:
                console.print("[bold yellow]Note content cannot be empty. Press any key to continue.[/bold yellow]")
                _getch()
                continue

            notes_dir = selected_company_dir / "notes"
            new_note = Note(title=note_title, content=note_content, timestamp=datetime.datetime.now(datetime.UTC))
            new_note.to_file(notes_dir)
            console.print("[bold green]Note added. Press any key to continue.[/bold green]")
            _getch()
        elif char == 'N':
            console.print("\n[bold green]Editing an existing note...[/bold green]")
            notes_dir = selected_company_dir / "notes"
            if not notes_dir.exists() or not any(notes_dir.iterdir()):
                console.print("[bold yellow]No notes found to edit. Press any key to continue.[/bold yellow]")
                _getch()
                continue

            note_files = []
            for note_file in notes_dir.iterdir():
                if note_file.is_file() and note_file.suffix == ".md":
                    note_files.append(note_file)
            
            if not note_files:
                console.print("[bold yellow]No notes found to edit. Press any key to continue.[/bold yellow]")
                _getch()
                continue

            # Sort notes by timestamp for consistent display in fzf
            note_files.sort(key=lambda f: f.name, reverse=True)
            fzf_input = "\n".join([f.name for f in note_files])

            selected_note_filename = run_fzf(fzf_input)

            if selected_note_filename:
                selected_note_path = notes_dir / selected_note_filename
                editor_command = get_editor_command()
                if editor_command:
                    try:
                        subprocess.run([editor_command, str(selected_note_path)], check=True)
                        console.print("[bold green]Note edited. Press any key to continue.[/bold green]")
                    except Exception as e:
                        console.print(f"[bold red]Error opening editor: {e}. Press any key to continue.[/bold red]")
                else:
                    console.print("[bold red]No editor configured. Please configure an editor in your cocli_config.toml. Press any key to continue.[/bold red]")
            else:
                console.print("[bold yellow]No note selected for editing. Press any key to continue.[/bold yellow]")
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
) -> None:
    """
    View all meetings for a specific company.
    """
    companies_dir = paths.companies.path
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
) -> None:
    """
    Open the company's folder in nvim.
    """
    companies_dir = paths.companies.path
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
