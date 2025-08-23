import typer
import datetime
import subprocess
import webbrowser
import yaml
from pathlib import Path
from typing import Optional, List, Any
from pytz import timezone
from tzlocal import get_localzone

from rich.console import Console
from rich.markdown import Markdown
from ..core.utils import _getch # Import _getch for interactive input
from .add_meeting import _add_meeting_logic # Import add_meeting command
from fuzzywuzzy import process # Added for fuzzy search

from ..core.config import get_companies_dir
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

        # Recent Meetings
        markdown_output += "\n---\n\n## Recent Meetings\n\n"
        recent_meetings = []
        if meetings_dir.exists():
            for meeting_file in sorted(meetings_dir.iterdir()):
                if meeting_file.is_file() and meeting_file.suffix == ".md":
                    try:
                        # Parse filename: YYYY-MM-DDTHHMMZ-slugified-title.md
                        filename_parts = meeting_file.name.split('-')
                        datetime_str = filename_parts[0] # YYYY-MM-DDTHHMMZ

                        # Handle both YYYY-MM-DDTHHMMZ and YYYY-MM-DD formats
                        if 'T' in datetime_str and datetime_str.endswith('Z'):
                            meeting_datetime_utc = datetime.datetime.strptime(datetime_str, '%Y-%m-%dT%H%MZ').replace(tzinfo=timezone('UTC'))
                        else:
                            # Fallback for older format or if only date is present
                            meeting_datetime_utc = datetime.datetime.strptime(datetime_str, '%Y-%m-%d').replace(tzinfo=timezone('UTC'))

                        local_tz = get_localzone()
                        meeting_datetime_local = meeting_datetime_utc.astimezone(local_tz)

                        six_months_ago_local = datetime.datetime.now(local_tz) - datetime.timedelta(days=180)
                        if meeting_datetime_local >= six_months_ago_local:
                            title_parts = filename_parts[1:] # Skip datetime part
                            meeting_title = (
                                " ".join(title_parts).replace(".md", "").replace("-", " ")
                                if title_parts
                                else "Untitled Meeting"
                            )
                            recent_meetings.append(
                                (meeting_datetime_local, meeting_file, meeting_title)
                            )
                    except (ValueError, IndexError):
                        pass

        if recent_meetings:
            for meeting_datetime_local, meeting_file, meeting_title in sorted(
                recent_meetings, key=lambda x: x[0], reverse=True
            ):
                markdown_output += (
                    f"- {meeting_datetime_local.strftime('%Y-%m-%d %H:%M %Z')}: [{meeting_title}]({meeting_file.name})\n"
                )
        else:
            markdown_output += "No recent meetings found.\n"

        console.print(Markdown(markdown_output))
        console.print("\n[bold yellow]Press 'a' to add meeting, 'e' to edit _index.md, 'w' to open website, 'q' to quit.[/bold yellow]")

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
        _display_company_details(company_name, selected_company_dir, frontmatter_data)
        char = _getch()

        if char == 'a':
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
        elif char == 'q':
            console.print("[bold green]Exiting company context.[/bold green]")
            break
        else:
            console.print(f"[bold red]Invalid option: '{char}'. Press 'a', 'e', 'w', or 'q'.[/bold red]")
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