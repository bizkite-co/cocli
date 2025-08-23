import typer
import datetime
import subprocess
import yaml
from pathlib import Path
from typing import Optional, List, Any

from rich.console import Console
from rich.markdown import Markdown
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
    companies_dir = get_companies_dir()
    company_slug = slugify(company_name)
    selected_company_dir = companies_dir / company_slug

    if not selected_company_dir.exists():
        # Fuzzy search for company if exact match not found
        company_names = [d.name for d in companies_dir.iterdir() if d.is_dir()]
        matches = process.extractOne(company_name, company_names)
        if matches and matches[1] >= 80:  # 80% similarity threshold
            if typer.confirm("Do you want to view this company instead?"):
                selected_company_dir = companies_dir / slugify(matches[0])
            else:
                print("Operation cancelled.")
                raise typer.Exit()
        else:
            print(f"Company '{company_name}' not found.")
            raise typer.Exit(code=1)




    # Display company details
    company_name = selected_company_dir.name
    index_path = selected_company_dir / "_index.md"
    tags_path = selected_company_dir / "tags.lst"
    meetings_dir = selected_company_dir / "meetings"

    markdown_output = ""

    # Company Details
    markdown_output += "\n# Company Details\n\n"
    if index_path.exists():
        content = index_path.read_text()
        # Extract YAML frontmatter
        if content.startswith("---") and "---" in content[3:]:
            frontmatter_str, markdown_content = content.split("---", 2)[1:]
            try:
                frontmatter_data = yaml.safe_load(frontmatter_str)
                if frontmatter_data:
                    for key, value in frontmatter_data.items():
                        if key != "name":
                            # Special handling for 'Domain' to make it a clickable link
                            if key == "domain" and isinstance(value, str):
                                markdown_output += f"- {key.replace('_', ' ').title()}: [{value}](http://{value})\n"
                            else:
                                markdown_output += f"- {key.replace('_', ' ').title()}: {value}\n"
            except yaml.YAMLError as e:
                markdown_output += f"Error parsing YAML frontmatter: {e}\n"
            markdown_output += f"\n{markdown_content.strip()}\n"
        else:
            markdown_output += f"\n{content.strip()}\n"
    else:
        markdown_output += f"No _index.md found for {company_name}.\n"

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
                    date_str = meeting_file.name.split("-")[0:3]
                    meeting_date = datetime.datetime.strptime(
                        "-".join(date_str), "%Y-%m-%d"
                    ).date()

                    six_months_ago = datetime.date.today() - datetime.timedelta(
                        days=180
                    )
                    if meeting_date >= six_months_ago:
                        # Extract title from filename if available
                        title_parts = meeting_file.name.split("-")[3:]
                        meeting_title = (
                            " ".join(title_parts).replace(".md", "").replace("-", " ")
                            if title_parts
                            else "Untitled Meeting"
                        )
                        recent_meetings.append(
                            (meeting_date, meeting_file, meeting_title)
                        )
                except ValueError:
                    pass

    if recent_meetings:
        for meeting_date, meeting_file, meeting_title in sorted(
            recent_meetings, key=lambda x: x[0], reverse=True
        ):
            markdown_output += (
                f"- {meeting_date.isoformat()}: [{meeting_title}]({meeting_file.name})\n"
            )
    else:
        markdown_output += "No recent meetings found.\n"

    # Options
    markdown_output += "\n---\n\n## Options\n\n"
    markdown_output += f"- To view all meetings: `cocli view-meetings {company_name}`\n"
    markdown_output += f"- To add a new meeting: `cocli add-meeting {company_name}`\n"
    markdown_output += f"- To open company folder in nvim: `cocli open-company_folder {company_name}`\n"

    console.print(Markdown(markdown_output))

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