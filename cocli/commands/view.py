import typer
import datetime
import subprocess
import re
import webbrowser
import yaml
import os
from pathlib import Path
from typing import Optional, List, Any
from pytz import timezone
from tzlocal import get_localzone

from rich.console import Console
from rich.markdown import Markdown
from ..core.utils import _getch # Import _getch for interactive input
from .add_meeting import _add_meeting_logic # Import add_meeting command
from fuzzywuzzy import process # Added for fuzzy search

from ..core.config import get_companies_dir, get_people_dir
from ..core.utils import slugify

console = Console()
app = typer.Typer()

@app.command()
def view_company(
    company_name: str = typer.Argument(..., help="Name of the company to view.")
):
    """
    View details of a specific company.
    """
    _interactive_view_company(company_name)

def _interactive_view_company(company_name: str):
    companies_dir = get_companies_dir()
    company_slug = slugify(company_name)
    selected_company_dir = companies_dir / company_slug

    if not selected_company_dir.exists():
        company_names = [d.name for d in companies_dir.iterdir() if d.is_dir()]
        matches = process.extractOne(company_name, company_names)
        if matches and matches[1] >= 80:
            if typer.confirm(f"Company '{company_name}' not found. Do you want to view '{matches[0]}' instead?"):
                selected_company_dir = companies_dir / slugify(matches[0])
                company_name = matches[0] # Update company_name to the matched one
            else:
                print("Operation cancelled.")
                raise typer.Exit()
        else:
            print(f"Company '{company_name}' not found.")
            raise typer.Exit(code=1)

    def _display_company_details(company_name: str, selected_company_dir: Path, frontmatter_data: dict):
        console.clear() # Clear console for fresh display
        index_path = selected_company_dir / "_index.md"
        tags_path = selected_company_dir / "tags.lst"
        meetings_dir = selected_company_dir / "meetings"

        markdown_output = ""

        # Company Details
        markdown_output += "\n# Company Details\n\n"
        if frontmatter_data:
            for key, value in frontmatter_data.items():
                if key != "name":
                    if key == "domain" and isinstance(value, str):
                        markdown_output += f"- {key.replace('_', ' ').title()}: [{value}](http://{value})\n"
                    elif key == "phone_number" and isinstance(value, str):
                        markdown_output += f"- {key.replace('_', ' ').title()}: {value} (Press 'p' to call)\n"
                    else:
                        markdown_output += f"- {key.replace('_', ' ').title()}: {value}\n"
            # Append markdown content after frontmatter
            content = index_path.read_text()
            if content.startswith("---") and "---" in content[3:]:
                _, markdown_content = content.split("---", 2)[1:]
                markdown_output += f"\n{markdown_content.strip()}\n"
            else:
                markdown_output += f"\n{content.strip()}\n"
        else:
            markdown_output += f"No _index.md found for {company_name} or no frontmatter.\n"

        # Tags
        markdown_output += "\n---\n\n## Tags\n\n"
        if tags_path.exists():
            tags = tags_path.read_text().strip().splitlines()
            markdown_output += ", ".join(tags) + "\n"
        else:
            markdown_output += "No tags found.\n"

        next_meetings = []
        recent_meetings = []
        past_meetings = [] # Not displayed, but good for categorization

        if meetings_dir.exists():
            now_local = datetime.datetime.now(get_localzone())
            six_months_ago_local = now_local - datetime.timedelta(days=180)

            for meeting_file in sorted(meetings_dir.iterdir()):
                if meeting_file.is_file() and meeting_file.suffix == ".md":
                    try:
                        match = re.match(r"^(\d{4}-\d{2}-\d{2}(?:T\d{4}Z)?)-?(.*)\.md$", meeting_file.name)
                        if not match:
                            raise ValueError("Filename does not match expected pattern.")

                        datetime_str = match.group(1)
                        title_slug = match.group(2)

                        if 'T' in datetime_str and datetime_str.endswith('Z'):
                            meeting_datetime_utc = datetime.datetime.strptime(datetime_str, '%Y-%m-%dT%H%MZ').replace(tzinfo=timezone('UTC'))
                        else:
                            meeting_datetime_utc = datetime.datetime.strptime(datetime_str, '%Y-%m-%d').replace(tzinfo=timezone('UTC'))

                        local_tz = get_localzone()
                        meeting_datetime_local = meeting_datetime_utc.astimezone(local_tz)
                        meeting_title = title_slug.replace("-", " ") if title_slug else "Untitled Meeting"

                        if meeting_datetime_local > now_local:
                            next_meetings.append((meeting_datetime_local, meeting_file, meeting_title))
                        elif meeting_datetime_local >= six_months_ago_local:
                            recent_meetings.append((meeting_datetime_local, meeting_file, meeting_title))
                        else:
                            past_meetings.append((meeting_datetime_local, meeting_file, meeting_title))
                    except (ValueError, IndexError):
                        pass

        # Sort meetings
        next_meetings.sort(key=lambda x: x[0]) # Ascending for next meetings
        recent_meetings.sort(key=lambda x: x[0], reverse=True) # Descending for recent meetings

        all_displayable_meetings = []
        meeting_counter = 1

        # Next Meetings
        markdown_output += "\n---\n\n## Next Meetings\n\n"
        if next_meetings:
            for meeting_datetime_local, meeting_file, meeting_title in next_meetings:
                markdown_output += (
                    f"- {meeting_counter}. {meeting_datetime_local.strftime('%Y-%m-%d %H:%M %Z')}: [{meeting_title}]({meeting_file.name})\n"
                )
                all_displayable_meetings.append((meeting_counter, meeting_file))
                meeting_counter += 1
        else:
            markdown_output += "No upcoming meetings found.\n"

        # Recent Meetings
        markdown_output += "\n---\n\n## Recent Meetings\n\n"
        if recent_meetings:
            for meeting_datetime_local, meeting_file, meeting_title in recent_meetings:
                markdown_output += (
                    f"- {meeting_counter}. {meeting_datetime_local.strftime('%Y-%m-%d %H:%M %Z')}: [{meeting_title}]({meeting_file.name})\n"
                )
                all_displayable_meetings.append((meeting_counter, meeting_file))
                meeting_counter += 1
        else:
            markdown_output += "No recent meetings found.\n"

        # Return the mapping of displayed number to file path
        return markdown_output, {num: file for num, file in all_displayable_meetings}

    index_path = selected_company_dir / "_index.md"
    frontmatter_data = {}
    if index_path.exists():
        content = index_path.read_text()
        if content.startswith("---") and "---" in content[3:]:
            frontmatter_str, _ = content.split("---", 2)[1:]
            try:
                frontmatter_data = yaml.safe_load(frontmatter_str) or {}
            except yaml.YAMLError as e:
                console.print(f"Error parsing YAML frontmatter: {e}")

    while True:
        markdown_content, meeting_map = _display_company_details(company_name, selected_company_dir, frontmatter_data)
        console.print(Markdown(markdown_content))
        console.print("\n[bold yellow]Press 'a' to add meeting, 'c' to add contact, 't' to add tag, 'e' to edit _index.md, 'w' to open website, 'p' to call, 'm' to select meeting, 'f' to go back to fuzzy finder, 'q' to quit.[/bold yellow]")
        char = _getch()

        if char == 'f':
            from .fz import fz
            console.clear()
            fz()
            break
        elif char == 'a':
            console.print("\n[bold green]Adding a new meeting...[/bold green]")
            meeting_date_str = typer.prompt("Enter meeting date (e.g., 'today', 'next Monday', '2025-12-25')")
            _add_meeting_logic(company_name=company_name, date_str=meeting_date_str)
            console.print("[bold green]Meeting added. Press any key to continue.[/bold green]")
            _getch() # Wait for a key press to clear the message
        elif char == 'e':
            console.print("\n[bold green]Opening _index.md in Vim...[/bold green]")
            index_path = selected_company_dir / "_index.md"
            try:
                subprocess.run(["vim", str(index_path)], check=True)
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
                    _add_meeting_logic(company_name=company_name, date_str="today", title_str="Google Voice Call", phone_number_str=phone_number)
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

            people_files = [f.name for f in people_dir.iterdir() if f.is_file() and f.suffix == '.md']
            if not people_files:
                console.print("[bold red]No people found in the people directory. Press any key to continue.[/bold red]")
                _getch()
                continue

            fzf_input = "\n".join(people_files)
            try:
                process = subprocess.run(
                    ["fzf"],
                    input=fzf_input,
                    stdout=subprocess.PIPE,
                    text=True,
                    check=True
                )
                selected_person_file = process.stdout.strip()

                if selected_person_file:
                    contacts_dir = selected_company_dir / "contacts"
                    contacts_dir.mkdir(exist_ok=True)
                    person_path = people_dir / selected_person_file
                    contact_symlink = contacts_dir / selected_person_file

                    if contact_symlink.exists():
                        console.print(f"[bold yellow]Contact ''{selected_person_file}'' already exists. Press any key to continue.[/bold yellow]")
                    else:
                        os.symlink(person_path, contact_symlink)
                        console.print(f"[bold green]Contact ''{selected_person_file}'' added. Press any key to continue.[/bold green]")
                else:
                    console.print("[bold yellow]No person selected. Press any key to continue.[/bold yellow]")

            except subprocess.CalledProcessError:
                console.print("[bold yellow]Contact selection cancelled. Press any key to continue.[/bold yellow]")
            except Exception as e:
                console.print(f"[bold red]Error adding contact: {e}. Press any key to continue.[/bold red]")
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
            console.print(f"[bold red]Invalid option: '{char}'. Press 'a', 'e', 'w', 'p', 'm', or 'q'.[/bold red]")
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
        print(f"Company '{company_name}' not found.")
        raise typer.Exit(code=1)

    if not meetings_dir.exists() or not any(meetings_dir.iterdir()):
        print(f"No meetings found for '{company_name}'.")
        return

    print(f"\n--- All Meetings for {company_name} ---")
    for meeting_file in sorted(meetings_dir.iterdir()):
        if meeting_file.is_file() and meeting_file.suffix == ".md":
            try:
                date_str = meeting_file.name.split("-")[0:3]
                meeting_date = datetime.datetime.strptime(
                    "-".join(date_str), "%Y-%m-%d"
                ).date()
                print(f"- {meeting_date.isoformat()}: {meeting_file.name}")
            except ValueError:
                print(f"- Malformed meeting file: {meeting_file.name}")


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
        print(f"Company '{company_name}' not found.")
        raise typer.Exit(code=1)

    try:
        subprocess.run(["nvim", str(company_dir)], check=True)
    except Exception as e:
        print(f"Error opening folder in nvim: {e}")
        raise typer.Exit(code=1)