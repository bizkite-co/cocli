import datetime
import re
import shutil
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from tzlocal import get_localzone

from ..application.services import ServiceContainer
from ..core.config import get_campaign
from ..models.companies.meeting import CompanyMeeting

console = Console()
app = typer.Typer()


def _format_meeting_for_fzf(meeting: CompanyMeeting) -> str:
    """Formats a meeting object into a string suitable for fzf display.

    Includes short datetime and company name, with file path embedded.
    """
    now_local = datetime.datetime.now(get_localzone())

    if meeting.datetime_local.date() == now_local.date():
        # If today, show only hours and minutes
        display_datetime = meeting.datetime_local.strftime("%H:%M")
    else:
        # Otherwise, show full date and time
        display_datetime = meeting.datetime_local.strftime("%Y-%m-%d %H:%M")

    # Escape potential problematic characters for fzf display
    escaped_company_name = (
        meeting.company_name.replace("\n", " ").replace('"', "'")
    )
    escaped_title = meeting.title.replace("\n", " ").replace('"', "'")

    # The string that fzf will display to the user
    display_text = (
        f"{display_datetime} - {escaped_company_name} - {escaped_title}"
    )

    # The full string passed to fzf, with the full path embedded for later extraction
    # fzf will display 'display_text' and allow searching on it,
    # but the full path is still available after the ' -- ' separator.
    formatted_string = f"{display_text} -- {meeting.file_path.as_posix()}"

    return formatted_string


@app.command(name="next", help="List and select upcoming meetings.")
def next_meetings() -> None:
    """Lists upcoming meetings and allows interactive selection."""
    if not shutil.which("fzf"):
        console.print("[bold red]Error:[/bold red] 'fzf' command not found.")
        console.print(
            "Please install fzf to use this feature. (e.g., `brew install fzf` or `sudo apt install fzf`)"
        )
        raise typer.Exit(code=1)

    campaign = get_campaign() or "default"
    services = ServiceContainer(campaign_name=campaign)
    upcoming_meetings = services.meeting_service.get_upcoming_meetings()

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
            stderr=sys.stderr,  # Reverted to sys.stderr for fzf interactive display
            text=True,
            check=True,
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
                console.print(
                    f"[bold red]Error:[/bold red] Could not parse selected item: '{selected_item}'"
                )
        else:
            console.print("No meeting selected.")

    except subprocess.CalledProcessError as e:
        if e.returncode == 130:  # fzf exit code for Ctrl-C
            console.print("Fuzzy search cancelled.")
        else:
            console.print(
                f"[bold red]Error during fzf selection:[/bold red] {e.stderr.strip()}"
            )
        raise typer.Exit()
    except FileNotFoundError:
        console.print(
            "Error: 'fzf' command not found. Please ensure fzf is installed and in your PATH."
        )
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred:[/bold red] {e}")
        raise typer.Exit(code=1)


@app.command(name="recent", help="List and select recent meetings.")
def recent_meetings() -> None:
    """Lists recent meetings and allows interactive selection."""
    if not shutil.which("fzf"):
        console.print("[bold red]Error:[/bold red] 'fzf' command not found.")
        console.print(
            "Please install fzf to use this feature. (e.g., `brew install fzf` or `sudo apt install fzf`)"
        )
        raise typer.Exit(code=1)

    campaign = get_campaign() or "default"
    services = ServiceContainer(campaign_name=campaign)
    past_meetings = services.meeting_service.get_recent_meetings(days_limit=180)

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
            stderr=sys.stderr,  # Reverted to sys.stderr for fzf interactive display
            text=True,
            check=True,
        )
        selected_item = process.stdout.strip()

        if selected_item:
            match = re.search(r"-- (.+)$", selected_item)
            if match:
                selected_file_path = Path(match.group(1))
                console.print(f"Opening meeting: {selected_file_path.name}")
                subprocess.run(["nvim", str(selected_file_path)], check=True)
            else:
                console.print(
                    f"[bold red]Error:[/bold red] Could not parse selected item: '{selected_item}'"
                )
        else:
            console.print("No meeting selected.")

    except subprocess.CalledProcessError as e:
        if e.returncode == 130:  # fzf exit code for Ctrl-C
            console.print("Fuzzy search cancelled.")
        else:
            console.print(
                f"[bold red]Error during fzf selection:[/bold red] {e.stderr.strip()}"
            )
        raise typer.Exit()
    except FileNotFoundError:
        console.print(
            "Error: 'fzf' command not found. Please ensure fzf is installed and in your PATH."
        )
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred:[/bold red] {e}")
        raise typer.Exit(code=1)