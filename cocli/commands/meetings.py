import typer
import subprocess
import datetime
import re
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import sys # Import sys

from rich.console import Console
from pytz import timezone
from tzlocal import get_localzone
import yaml

from ..core.config import get_companies_dir
from ..core.utils import slugify

console = Console()
app = typer.Typer()

@dataclass
class Meeting:
    datetime_utc: datetime.datetime
    datetime_local: datetime.datetime
    company_name: str
    title: str
    file_path: Path

def _get_all_meetings() -> List[Meeting]:
    """
    Gathers all meeting data from all companies.
    """
    all_meetings: List[Meeting] = []
    companies_dir = get_companies_dir()
    local_tz = get_localzone()

    for company_dir in companies_dir.iterdir():
        if company_dir.is_dir():
            company_name = company_dir.name.replace("-", " ").title()
            meetings_dir = company_dir / "meetings"

            if meetings_dir.exists():
                for meeting_file in meetings_dir.iterdir():
                    if meeting_file.is_file() and meeting_file.suffix == ".md":
                        try:
                            # Parse filename: YYYY-MM-DDTHHMMZ-slugified-title.md
                            # Use regex to extract the datetime part from the filename
                            match = re.match(r"^(\d{4}-\d{2}-\d{2}(?:T\d{4}Z)?)-", meeting_file.name)
                            if match:
                                datetime_str_raw = match.group(1)
                            else:
                                console.print(f"[bold yellow]Warning:[/bold yellow] Could not extract datetime from filename {meeting_file.name}. Skipping.")
                                continue

                            # Handle both YYYY-MM-DDTHHMMZ and YYYY-MM-DD formats
                            if 'T' in datetime_str_raw and datetime_str_raw.endswith('Z'):
                                datetime_utc = datetime.datetime.strptime(datetime_str_raw, '%Y-%m-%dT%H%MZ').replace(tzinfo=timezone('UTC'))
                            else:
                                # Fallback for older format or if only date is present
                                datetime_utc = datetime.datetime.strptime(datetime_str_raw, '%Y-%m-%d').replace(tzinfo=timezone('UTC'))

                            datetime_local = datetime_utc.astimezone(local_tz)

                            # Extract title from filename
                            # Extract title by removing the datetime part and .md extension
                            title_start_index = len(datetime_str_raw) + 1 # +1 for the hyphen
                            meeting_title_raw = meeting_file.name[title_start_index:].replace(".md", "")
                            meeting_title = meeting_title_raw.replace("-", " ").strip()
                            if not meeting_title:
                                meeting_title = "Untitled Meeting"

                            # Read frontmatter for more accurate title if available
                            content = meeting_file.read_text()
                            frontmatter_data = {}
                            if content.startswith("---") and "---" in content[3:]:
                                frontmatter_str, _ = content.split("---", 2)[1:]
                                try:
                                    frontmatter_data = yaml.safe_load(frontmatter_str) or {}
                                    if 'title' in frontmatter_data:
                                        meeting_title = frontmatter_data['title']
                                except yaml.YAMLError:
                                    pass # Ignore YAML errors

                            all_meetings.append(
                                Meeting(
                                    datetime_utc=datetime_utc,
                                    datetime_local=datetime_local,
                                    company_name=company_name,
                                    title=meeting_title,
                                    file_path=meeting_file,
                                )
                            )
                        except (ValueError, IndexError, FileNotFoundError) as e:
                            console.print(f"[bold yellow]Warning:[/bold yellow] Could not parse meeting file {meeting_file.name}: {e}")
                            continue
    return all_meetings

def _format_meeting_for_fzf(meeting: Meeting) -> str:
    """
    Formats a meeting object into a string suitable for fzf display.
    Includes short datetime and company name, with file path embedded.
    """
    now_local = datetime.datetime.now(get_localzone())

    if meeting.datetime_local.date() == now_local.date():
        # If today, show only hours and minutes
        display_datetime = meeting.datetime_local.strftime('%H:%M')
    else:
        # Otherwise, show full date and time
        display_datetime = meeting.datetime_local.strftime('%Y-%m-%d %H:%M')

    # Escape potential problematic characters for fzf display
    escaped_company_name = meeting.company_name.replace('\n', ' ').replace('"', "'")
    escaped_title = meeting.title.replace('\n', ' ').replace('"', "'")

    # The string that fzf will display to the user
    display_text = f"{display_datetime} - {escaped_company_name} - {escaped_title}"

    # The full string passed to fzf, with the full path embedded for later extraction
    # fzf will display 'display_text' and allow searching on it,
    # but the full path is still available after the ' -- ' separator.
    formatted_string = f"{display_text} -- {meeting.file_path.as_posix()}"

    return formatted_string

@app.command(name="next", help="List and select upcoming meetings.")
def next_meetings():
    """
    Lists upcoming meetings and allows interactive selection.
    """
    if not shutil.which("fzf"):
        console.print("[bold red]Error:[/bold red] 'fzf' command not found.")
        console.print("Please install fzf to use this feature. (e.g., `brew install fzf` or `sudo apt install fzf`)")
        raise typer.Exit(code=1)

    all_meetings = _get_all_meetings()
    now_local = datetime.datetime.now(get_localzone())

    upcoming_meetings = sorted(
        [m for m in all_meetings if m.datetime_local > now_local],
        key=lambda m: m.datetime_local
    )

    if not upcoming_meetings:
        console.print("No upcoming meetings found.")
        raise typer.Exit()

    fzf_input_lines = [_format_meeting_for_fzf(m) for m in upcoming_meetings]
    fzf_input = "\n".join(fzf_input_lines)

    try:
        process = subprocess.run(
            ["fzf"],
            input=fzf_input,
            stdout=subprocess.PIPE,
            stderr=sys.stderr, # Reverted to sys.stderr for fzf interactive display
            text=True,
            check=True
        )
        selected_item = process.stdout.strip()

        if selected_item:
            # Extract file path from the embedded string
            match = re.search(r"-- (.+)$", selected_item)
            if match:
                selected_file_path = Path(match.group(1))
                console.print(f"Opening meeting: {selected_file_path.name}")
                subprocess.run(["nvim", str(selected_file_path)], check=True)
            else:
                console.print(f"[bold red]Error:[/bold red] Could not parse selected item: '{selected_item}'")
        else:
            console.print("No meeting selected.")

    except subprocess.CalledProcessError as e:
        if e.returncode == 130: # fzf exit code for Ctrl-C
            console.print("Fuzzy search cancelled.")
        else:
            console.print(f"[bold red]Error during fzf selection:[/bold red] {e.stderr.strip()}")
        raise typer.Exit()
    except FileNotFoundError:
        console.print("Error: 'fzf' command not found. Please ensure fzf is installed and in your PATH.")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred:[/bold red] {e}")
        raise typer.Exit(code=1)

@app.command(name="recent", help="List and select recent meetings.")
def recent_meetings():
    """
    Lists recent meetings and allows interactive selection.
    """
    if not shutil.which("fzf"):
        console.print("[bold red]Error:[/bold red] 'fzf' command not found.")
        console.print("Please install fzf to use this feature. (e.g., `brew install fzf` or `sudo apt install fzf`)")
        raise typer.Exit(code=1)

    all_meetings = _get_all_meetings()
    now_local = datetime.datetime.now(get_localzone())
    six_months_ago_local = now_local - datetime.timedelta(days=180)

    past_meetings = sorted(
        [m for m in all_meetings if m.datetime_local < now_local and m.datetime_local >= six_months_ago_local],
        key=lambda m: m.datetime_local,
        reverse=True
    )

    if not past_meetings:
        console.print("No recent meetings found.")
        raise typer.Exit()

    fzf_input_lines = [_format_meeting_for_fzf(m) for m in past_meetings]
    fzf_input = "\n".join(fzf_input_lines)

    try:
        process = subprocess.run(
            ["fzf"],
            input=fzf_input,
            stdout=subprocess.PIPE,
            stderr=sys.stderr, # Reverted to sys.stderr for fzf interactive display
            text=True,
            check=True
        )
        selected_item = process.stdout.strip()

        if selected_item:
            match = re.search(r"-- (.+)$", selected_item)
            if match:
                selected_file_path = Path(match.group(1))
                console.print(f"Opening meeting: {selected_file_path.name}")
                subprocess.run(["nvim", str(selected_file_path)], check=True)
            else:
                console.print(f"[bold red]Error:[/bold red] Could not parse selected item: '{selected_item}'")
        else:
            console.print("No meeting selected.")

    except subprocess.CalledProcessError as e:
        if e.returncode == 130: # fzf exit code for Ctrl-C
            console.print("Fuzzy search cancelled.")
        else:
            console.print(f"[bold red]Error during fzf selection:[/bold red] {e.stderr.strip()}")
        raise typer.Exit()
    except FileNotFoundError:
        console.print("Error: 'fzf' command not found. Please ensure fzf is installed and in your PATH.")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred:[/bold red] {e}")
        raise typer.Exit(code=1)