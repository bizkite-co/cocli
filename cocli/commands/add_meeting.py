import typer
import datetime
import subprocess
from typing import Optional
from pathlib import Path

from ..core.config import get_companies_dir
from ..core.utils import slugify

app = typer.Typer()

@app.command()
def add_meeting(
    company_name: str = typer.Option(
        ..., "--company", "-c", help="Name of the company"
    ),
    date: Optional[str] = typer.Option(
        None,
        "--date",
        "-d",
        help="Date of the meeting (YYYY-MM-DD). Defaults to today.",
    ),
    time: Optional[str] = typer.Option(
        None, "--time", "-t", help="Time of the meeting (HH:MM)."
    ),
    title: Optional[str] = typer.Option(
        None, "--title", "-T", help="Title of the meeting."
    ),
):
    """
    Add a new meeting for a company.
    """
    companies_dir = get_companies_dir()
    company_slug = slugify(company_name)
    company_dir = companies_dir / company_slug
    meetings_dir = company_dir / "meetings"
    meetings_dir.mkdir(parents=True, exist_ok=True)

    meeting_date = datetime.date.today()
    if date:
        try:
            meeting_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            print("Invalid date format. Please use YYYY-MM-DD.")
            raise typer.Exit(code=1)

    meeting_filename = f"{meeting_date.isoformat()}"
    if title:
        meeting_filename += f"-{slugify(title)}"
    meeting_filename += ".md"
    meeting_path = meetings_dir / meeting_filename

    meeting_content = f"""---
date: {meeting_date.isoformat()}
company: {company_name}
"""
    if time:
        meeting_content += f"time: {time}\n"
    if title:
        meeting_content += f"title: {title}\n"
    meeting_content += "---\n\n"

    try:
        meeting_path.write_text(meeting_content)
        print(f"Meeting added for '{company_name}' on {meeting_date.isoformat()}")
        subprocess.run(["nvim", meeting_path], check=True)
    except Exception as e:
        print(f"Error adding meeting: {e}")
        raise typer.Exit(code=1)