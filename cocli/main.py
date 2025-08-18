from pathlib import Path

import typer
from typing_extensions import Annotated
from typing import Optional, List
from rich.console import Console
from rich.markdown import Markdown
from . import importers
from .scrapers import google_maps
from .core import (
    Company,
    Person,
    create_company_files,
    create_person_files,
    slugify,
    get_people_dir,
    get_companies_dir,
    get_cocli_base_dir,
)
import os
import datetime
import subprocess
import yaml
from fuzzywuzzy import process # Added for fuzzy search

console = Console()

app = typer.Typer(no_args_is_help=True)


@app.command()
def add(
    company_name: str = typer.Option(
        ..., "--company", "-c", help="Name of the company"
    ),
    person_name: Optional[str] = typer.Option(
        None, "--person", "-p", help="Name of the person"
    ),
):
    """
    Add a new company or a person to an existing company.
    """
    companies_dir = get_companies_dir()
    company_dir = companies_dir / slugify(company_name)

    if not company_dir.exists():
        create_company_files(company_name, company_dir)
        print(f"Company '{company_name}' created at {company_dir}")
    else:
        print(f"Company '{company_name}' already exists at {company_dir}")

    if person_name:
        people_dir = get_people_dir()
        person_dir = people_dir / slugify(person_name)
        if not person_dir.exists():
            create_person_files(person_name, person_dir, company_name)
            print(f"Person '{person_name}' created at {person_dir}")
        else:
            print(f"Person '{person_name}' already exists at {person_dir}")


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


@app.command()
def find(
    query: str = typer.Argument(..., help="Search query for companies or people."),
    company_only: bool = typer.Option(
        False, "--company-only", "-c", help="Search only companies."
    ),
    person_only: bool = typer.Option(
        False, "--person-only", "-p", help="Search only people."
    ),
):
    """
    Find companies or people by name.
    """
    if company_only and person_only:
        print("Cannot use both --company-only and --person-only.")
        raise typer.Exit(code=1)

    companies_dir = get_companies_dir()
    people_dir = get_people_dir()

    results = []

    if not person_only:
        for company_dir in companies_dir.iterdir():
            if company_dir.is_dir():
                company = Company.from_directory(company_dir)
                if company and query.lower() in company.name.lower():
                    results.append(("company", company))

    if not company_only:
        for person_file in people_dir.iterdir(): # Changed from person_dir to person_file
            if person_file.is_file() and person_file.suffix == ".md": # Ensure it's a markdown file
                person = Person.from_directory(person_file) # Pass file path
                if person and query.lower() in person.name.lower():
                    results.append(("person", person))

    if not results:
        print(f"No companies or people found matching '{query}'.")
        return

    print("Found the following matches:")
    for item_type, item in results:
        if item_type == "company":
            print(f"- Company: {item.name}")
        else:
            print(f"- Person: {item.name} (Company: {item.company_name})")


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
            print(f"Company '{company_name}' not found. Did you mean '{matches[0]}'?")
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


@app.command()
def import_data(
    importer_name: str = typer.Argument(..., help="Name of the importer to use."),
    file_path: Path = typer.Argument(..., help="Path to the data file to import."),
):
    """
    Import data using a specified importer.
    """
    if not file_path.is_file():
        print(f"Error: File not found at {file_path}")
        raise typer.Exit(code=1)

    try:
        importer_func = getattr(importers, importer_name)
    except AttributeError:
        print(f"Error: Importer '{importer_name}' not found.")
        raise typer.Exit(code=1)

    try:
        importer_func(file_path)
        print(f"Data imported successfully using '{importer_name}'.")
    except Exception as e:
        print(f"Error during import: {e}")
        raise typer.Exit(code=1)


@app.command()
def scrape_google_maps(
    query: str = typer.Argument(..., help="Search query for Google Maps."),
    output_file: Path = typer.Option(
        "google_maps_results.json",
        "--output",
        "-o",
        help="Output JSON file for scraped data.",
    ),
):
    """
    Scrape data from Google Maps.
    """
    try:
        google_maps.scrape(query, output_file)
        print(f"Scraping completed. Results saved to {output_file}")
    except Exception as e:
        print(f"Error during scraping: {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
