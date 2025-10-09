import typer
import dateparser
import datetime
import subprocess
from typing import Optional
from pathlib import Path
from pytz import timezone
from tzlocal import get_localzone

from ..core.config import get_companies_dir
from ..core.utils import slugify

app = typer.Typer()

def _add_meeting_logic(company_name: str, date_str: Optional[str] = None, time_str: Optional[str] = None, title_str: Optional[str] = None, phone_number_str: Optional[str] = None):
    """
    Core logic for adding a new meeting.
    """
    companies_dir = get_companies_dir()
    company_slug = slugify(company_name)
    company_dir = companies_dir / company_slug
    meetings_dir = company_dir / "meetings"
    meetings_dir.mkdir(parents=True, exist_ok=True)

    local_tz = get_localzone()

    if date_str:
        if date_str.lower() == "now" or date_str.lower() == "today":
            parsed_datetime = datetime.datetime.now(local_tz)
        else:
            parsed_datetime = dateparser.parse(date_str, settings={'TIMEZONE': str(local_tz)})
        if not parsed_datetime:
            print("Invalid date/time format. Please provide a recognizable date/time string (e.g., 'today', 'tomorrow at 9am', 'next Monday', '2025-12-25 14:30').")
            raise typer.Exit(code=1)

        # If naive datetime, assume local timezone
        if parsed_datetime.tzinfo is None or parsed_datetime.tzinfo.utcoffset(parsed_datetime) is None:
            meeting_datetime_local = parsed_datetime.replace(tzinfo=local_tz)
        else:
            meeting_datetime_local = parsed_datetime.astimezone(local_tz)
    else:
        meeting_datetime_local = datetime.datetime.now(local_tz)

    # Convert to UTC for storage and filename
    meeting_datetime_utc = meeting_datetime_local.astimezone(timezone('UTC'))

    if not title_str:
        title_str = typer.prompt("Meeting Title")

    # Filename format: YYYY-MM-DDTHHMMZ-slugified-title.md
    meeting_filename = f"{meeting_datetime_utc.strftime('%Y-%m-%dT%H%MZ')}"
    if title_str:
        meeting_filename += f"-{slugify(title_str)}"
    meeting_filename += ".md"
    meeting_path = meetings_dir / meeting_filename

    meeting_content = f"""---
date: {meeting_datetime_utc.isoformat()}
company: {company_name}
"""
    # The time is now part of the date field, so no separate time field needed in frontmatter
    if title_str:
        meeting_content += f"title: {title_str}\n"
    if phone_number_str:
        meeting_content += f"phone_number: {phone_number_str}\n"
    meeting_content += "---\n\n"

    try:
        meeting_path.write_text(meeting_content)
        print(f"Meeting added for '{company_name}' on {meeting_datetime_local.strftime('%Y-%m-%d %H:%M %Z')}")
        subprocess.run(["nvim", meeting_path], check=True)
    except Exception as e:
        print(f"Error adding meeting: {e}")
        raise typer.Exit(code=1)

@app.command()
def add_meeting(
    company_name: str = typer.Option(
        ..., "--company", "-c", help="Name of the company"
    ),
    date: Optional[str] = typer.Option(
        None,
        "--date",
        "-d",
        help="Date of the meeting (e.g., 'today', 'tomorrow at 9am'). Defaults to now.",
    ),
    time: Optional[str] = typer.Option(
        None, "--time", "-t", help="Time of the meeting (HH:MM). This option is now deprecated, time should be included in --date."
    ),
    title: Optional[str] = typer.Option(
        None, "--title", "-T", help="Title of the meeting."
    ),
):
    """
    Add a new meeting for a company.
    """
    _add_meeting_logic(company_name=company_name, date_str=date, title_str=title)
    if time:
        print("[bold yellow]Warning:[/bold yellow] The --time option is deprecated. Please include time directly in the --date option (e.g., `--date 'tomorrow at 9am'`).")