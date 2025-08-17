from pathlib import Path

import typer
from typing_extensions import Annotated
from typing import Optional, List
from . import importers
from .scrapers import google_maps
from .core import Company, Person, create_company_files, create_person_files, slugify, get_people_dir, get_companies_dir, get_cocli_base_dir
import os
import datetime
import subprocess
import yaml
from fuzzywuzzy import fuzz # Import fuzzywuzzy

# Create the main Typer application
app = typer.Typer(no_args_is_help=True)

@app.command(name="importer")
def import_data(
    format: str = typer.Argument(..., help="The name of the importer to use (e.g., 'lead-sniper')."),
    filepath: Path = typer.Argument(..., help="The path to the file to import.", file_okay=True, dir_okay=False, readable=True)
):
    """
    Imports companies from a specified file using a given format.
    """
    importer_func = getattr(importers, format.replace('-', '_'), None)

    if importer_func:
        importer_func(filepath)
    else:
        print(f"Error: Importer '{format}' not found.")
        raise typer.Exit(code=1)

@app.command(name="scrape")
def scrape_data(
    tool: str = typer.Argument(..., help="The name of the scraper tool to use (e.g., 'google-maps')."),
    url: str = typer.Argument(..., help="The URL to scrape."),
    keyword: Optional[str] = typer.Option(None, "--keyword", "-k", help="Optional keyword to associate with the scraped data."),
    output_dir: Path = typer.Option(Path("temp"), "--output-dir", "-o", help="Directory to save the scraped CSV file."), # Changed default to Path("temp")
    max_results: int = typer.Option(50, "--max-results", "-m", help="Maximum number of results to scrape.")
):
    """
    Scrapes data using a specified tool and outputs it to a CSV file.
    """
    if tool == "google-maps":
        google_maps.scrape_google_maps(url, keyword, output_dir, max_results)
    else:
        print(f"Error: Scraper tool '{tool}' not found.")
        raise typer.Exit(code=1)

@app.command()
def add(
    company_name: Annotated[str, typer.Option("-c", "--company", help="Company name (e.g., 'My Company;example.com;Type').")] = "",
    person_name: Annotated[str, typer.Option("-p", "--person", help="Person name (e.g., 'John Doe;john@example.com;123-456-7890').")] = "",
):
    """
    Adds a new company or person, and can associate a person with a company.
    """
    company_slug = ""

    # Handle Company Creation
    if company_name:
        parts = company_name.split(';')
        name = parts[0].strip()
        domain = parts[1].strip() if len(parts) > 1 else None
        company_type = parts[2].strip() if len(parts) > 2 else "N/A"

        company = Company(name=name, domain=domain, type=company_type)
        company_dir = create_company_files(company)
        company_slug = slugify(name) # Get slug for potential person association

    # Handle Person Creation
    if person_name:
        parts = person_name.split(';')
        name = parts[0].strip()
        email = parts[1].strip() if len(parts) > 1 else None
        phone = parts[2].strip() if len(parts) > 2 else None

        person = Person(name=name, email=email, phone=phone)
        person_file = create_person_files(person)

        # Handle Association via Symlink
        if company_slug and person_file:
            company_dir = get_companies_dir() / company_slug
            contacts_dir = company_dir / "contacts"
            contacts_dir.mkdir(parents=True, exist_ok=True) # Ensure contacts dir exists

            person_slug = slugify(person.name)
            contact_link_path = contacts_dir / f"{person_slug}.md"

            if not contact_link_path.exists():
                print(f"Associating {person.name} with {company.name}...")
                os.symlink(person_file, contact_link_path)
            else:
                print(f"Association for {person.name} with {company.name} already exists.")

    if not company_name and not person_name:
        print("Error: No company or person details provided. Use -c or -p.")
        raise typer.Exit(code=1)

    print("Done.")

@app.command(name="add-meeting")
def add_meeting(
    company_name: Optional[str] = typer.Argument(None, help="Optional company name to add meeting to.")
):
    """
    Adds a new meeting to a selected company.
    """
    companies = [d.name for d in get_companies_dir().iterdir() if d.is_dir()]
    if not companies:
        print("No companies found. Please add a company first.")
        raise typer.Exit(code=1)

    selected_company_name = company_name
    if not selected_company_name:
        print("Available companies:")
        for i, c_name in enumerate(companies):
            print(f"{i+1}. {c_name}")

        while True:
            try:
                selection = typer.prompt("Select a company by number or name")
                if selection.isdigit():
                    selected_company_name = companies[int(selection) - 1]
                else:
                    selected_company_name = selection

                if selected_company_name not in companies:
                    print("Invalid selection. Please try again.")
                    continue
                break
            except (ValueError, IndexError):
                print("Invalid selection. Please try again.")
                continue

    company_slug = slugify(selected_company_name)
    company_dir = get_companies_dir() / company_slug
    meetings_dir = company_dir / "meetings"
    meetings_dir.mkdir(parents=True, exist_ok=True)

    meeting_title = typer.prompt("Enter meeting title")
    meeting_slug = slugify(meeting_title)

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d")
    filename = f"{timestamp}-{meeting_slug}.md"
    filepath = meetings_dir / filename

    if filepath.exists():
        print(f"Meeting file '{filename}' already exists. Opening existing file.")
    else:
        filepath.touch()
        print(f"Created meeting file: {filename}")

    editor = os.environ.get("EDITOR", "vim")
    try:
        subprocess.run([editor, str(filepath)], check=True)
    except FileNotFoundError:
        print(f"Error: Editor '{editor}' not found. Please ensure it's installed and in your PATH.")
        raise typer.Exit(code=1)
    except subprocess.CalledProcessError:
        print("Editor exited with an error.")
        raise typer.Exit(code=1)

    print("Done.")

@app.command()
def find(
    query: Optional[str] = typer.Argument(None, help="Optional search query to filter companies.")
):
    """
    Finds and displays information about a company or person.
    """
    company_dirs = [d for d in get_companies_dir().iterdir() if d.is_dir()]

    if not company_dirs:
        print("No companies found.")
        raise typer.Exit(code=1)

    selected_company_dir: Optional[Path] = None
    list_already_printed = False

    if query:
        # Fuzzy search for company name
        strong_matches = []
        for company_dir in company_dirs:
            score = fuzz.partial_ratio(query.lower(), company_dir.name.lower())
            if score >= 70: # Threshold for a good fuzzy match
                strong_matches.append((company_dir, score))

        strong_matches.sort(key=lambda x: x[1], reverse=True) # Sort by score, descending

        if len(strong_matches) == 1:
            selected_company_dir = strong_matches[0][0]
            print(f"Found best match: {selected_company_dir.name}")
        elif len(strong_matches) > 1:
            print(f"Multiple strong matches found for '{query}':")
            for i, (company_dir, score) in enumerate(strong_matches):
                print(f"{i+1}. {company_dir.name} (Score: {score})")
            # Set company_dirs to strong_matches for interactive selection
            company_dirs = [match[0] for match in strong_matches]
            query = None # Proceed to interactive selection
        else:
            print(f"No strong match found for '{query}'. Listing all companies.")
            query = None # Fallback to interactive mode

    if not selected_company_dir:
        if not list_already_printed: # Only print if not already printed
            print("Available companies:")
            for i, company_dir in enumerate(company_dirs):
                print(f"{i+1}. {company_dir.name}") # Corrected from c_name

        while True:
            try:
                selection = typer.prompt("Select a company by number or name")
                if selection.isdigit():
                    selected_company_dir = company_dirs[int(selection) - 1]
                else:
                    # Try to find an exact match by name
                    exact_match = next((d for d in company_dirs if d.name.lower() == slugify(selection).lower()), None)
                    if exact_match:
                        selected_company_dir = exact_match
                    else:
                        print("Invalid selection. Please try again.")
                        continue

                if not selected_company_dir.exists():
                    print("Selected company does not exist. Please try again.")
                    continue
                break
            except (ValueError, IndexError):
                print("Invalid selection. Please try again.")
                continue

    # Display company details
    company_name = selected_company_dir.name
    index_path = selected_company_dir / "_index.md"
    tags_path = selected_company_dir / "tags.lst"
    meetings_dir = selected_company_dir / "meetings"

    print("\n--- Company Details ---")
    if index_path.exists():
        content = index_path.read_text()
        # Extract YAML frontmatter
        if content.startswith("---") and "---" in content[3:]:
            frontmatter_str, markdown_content = content.split("---", 2)[1:]
            try:
                frontmatter_data = yaml.safe_load(frontmatter_str)
                if frontmatter_data:
                    for key, value in frontmatter_data.items():
                        if key != "name": # Name is already displayed as title
                            print(f"- {key.replace('_', ' ').title()}: {value}") # Removed bolding
            except yaml.YAMLError as e:
                print(f"Error parsing YAML frontmatter: {e}")
            print(markdown_content.strip())
        else:
            print(content.strip())
    else:
        print(f"No _index.md found for {company_name}.")

    print("\n--- Tags ---")
    if tags_path.exists():
        tags = tags_path.read_text().strip().splitlines()
        print(", ".join(tags))
    else:
        print("No tags found.")

    print("\n--- Recent Meetings ---")
    recent_meetings = []
    if meetings_dir.exists():
        for meeting_file in sorted(meetings_dir.iterdir()):
            if meeting_file.is_file() and meeting_file.suffix == ".md":
                try:
                    # Extract date from filename (YYYY-MM-DD-slug.md)
                    date_str = meeting_file.name.split('-')[0:3]
                    meeting_date = datetime.datetime.strptime("-".join(date_str), "%Y-%m-%d").date()

                    # Filter by last 6 months
                    six_months_ago = datetime.date.today() - datetime.timedelta(days=180)
                    if meeting_date >= six_months_ago:
                        recent_meetings.append((meeting_date, meeting_file))
                except ValueError:
                    # Ignore files with malformed dates
                    pass

    # Sort meetings by date ascending and limit to most recent 5
    recent_meetings.sort(key=lambda x: x[0])
    recent_meetings = recent_meetings[-5:]

    if recent_meetings:
        for date, meeting_file in recent_meetings:
            print(f"- {date.strftime('%Y-%m-%d')}: {meeting_file.stem}")
    else:
        print("No recent meetings found.")

    print("\n--- Options ---")
    print(f"To view all meetings: cocli view-meetings {company_name}")
    print(f"To add a new meeting: cocli add-meeting {company_name}")
    print(f"To open company folder in nvim: cocli open-company-folder {company_name}") # New option

    print("\nDone.")

@app.command(name="view-meetings")
def view_meetings(
    company_name: str = typer.Argument(..., help="The name of the company to view meetings for."),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Limit the number of meetings displayed."),
    since: Optional[str] = typer.Option(None, "--since", "-s", help="Display meetings since a specific date (YYYY-MM-DD)."),
):
    """
    Views all meetings for a given company, with optional filtering.
    """
    company_slug = slugify(company_name)
    company_dir = get_companies_dir() / company_slug
    meetings_dir = company_dir / "meetings"

    if not meetings_dir.exists():
        print(f"No meetings found for '{company_name}'.")
        raise typer.Exit(code=1)

    all_meetings = []
    for meeting_file in sorted(meetings_dir.iterdir()):
        if meeting_file.is_file() and meeting_file.suffix == ".md":
            try:
                date_str = meeting_file.name.split('-')[0:3]
                meeting_date = datetime.datetime.strptime("-".join(date_str), "%Y-%m-%d").date()
                all_meetings.append((meeting_date, meeting_file))
            except ValueError:
                pass # Ignore malformed dates

    filtered_meetings = all_meetings
    if since:
        try:
            since_date = datetime.datetime.strptime(since, "%Y-%m-%d").date()
            filtered_meetings = [m for m in filtered_meetings if m[0] >= since_date]
        except ValueError:
            print("Invalid --since date format. Please use YYYY-MM-DD.")
            raise typer.Exit(code=1)

    filtered_meetings.sort(key=lambda x: x[0]) # Sort by date ascending

    if limit:
        filtered_meetings = filtered_meetings[-limit:] # Get the most recent 'limit' meetings

    print(f"\n--- All Meetings for {company_name} ---")
    if filtered_meetings:
        for date, meeting_file in filtered_meetings:
            print(f"- {date.strftime('%Y-%m-%d')}: {meeting_file.stem}")
    else:
        print(f"No meetings found for '{company_name}' with the given filters.")

    print("\nDone.")

@app.command(name="open-company-folder")
def open_company_folder(
    company_name: str = typer.Argument(..., help="The name of the company to open the folder for.")
):
    """
    Opens the company's data folder in nvim.
    """
    company_slug = slugify(company_name)
    company_dir = get_companies_dir() / company_slug

    if not company_dir.exists():
        print(f"Error: Company folder for '{company_name}' not found at {company_dir}.")
        raise typer.Exit(code=1)

    editor = os.environ.get("EDITOR", "nvim") # Default to nvim for this command
    try:
        # Use subprocess.Popen to allow nvim to run in the background
        # and not block the CLI.
        subprocess.Popen([editor, str(company_dir)])
        print(f"Opened '{company_name}' folder in {editor}.")
    except FileNotFoundError:
        print(f"Error: Editor '{editor}' not found. Please ensure it's installed and in your PATH.")
        raise typer.Exit(code=1)
    except Exception as e:
        print(f"An unexpected error occurred while opening nvim: {e}")
        raise typer.Exit(code=1)

    print("Done.")

@app.command(name="data-path")
def data_path():
    """
    Prints the root data directory for cocli.
    """
    print(get_cocli_base_dir())
    # Removed typer.Exit(code=0)

@app.command(name="git-sync")
def git_sync():
    """
    Synchronizes the cocli data directory with its Git remote (pull and push).
    """
    data_dir = get_cocli_base_dir()
    if not (data_dir / ".git").is_dir():
        print(f"Error: Data directory '{data_dir}' is not a Git repository.")
        raise typer.Exit(code=1)

    print(f"Synchronizing Git repository at {data_dir}...")

    try:
        # Pull changes
        pull_result = subprocess.run(
            ["git", "pull"], cwd=data_dir, capture_output=True, text=True, check=True
        )
        print(pull_result.stdout.strip())
        if pull_result.stderr:
            print(pull_result.stderr.strip())

        # Push changes
        push_result = subprocess.run(
            ["git", "push"], cwd=data_dir, capture_output=True, text=True, check=True
        )
        print(push_result.stdout.strip())
        if push_result.stderr:
            print(push_result.stderr.strip())

        print("Git synchronization complete.")
    except subprocess.CalledProcessError as e:
        print(f"Error during Git sync: {e}")
        print(e.stdout)
        print(e.stderr)
        raise typer.Exit(code=1)
    except FileNotFoundError:
        print("Error: 'git' command not found. Please ensure Git is installed and in your PATH.")
        raise typer.Exit(code=1)
    # Removed typer.Exit(code=0)

@app.command(name="git-commit")
def git_commit(
    message: Annotated[str, typer.Option("-m", "--message", help="Commit message.")]
):
    """
    Commits changes in the cocli data directory to Git.
    """
    data_dir = get_cocli_base_dir()
    if not (data_dir / ".git").is_dir():
        print(f"Error: Data directory '{data_dir}' is not a Git repository.")
        raise typer.Exit(code=1)

    print(f"Committing changes in Git repository at {data_dir} with message: '{message}'...")

    try:
        # Add all changes
        add_result = subprocess.run(
            ["git", "add", "."], cwd=data_dir, capture_output=True, text=True, check=True
        )
        if add_result.stdout:
            print(add_result.stdout.strip())
        if add_result.stderr:
            print(add_result.stderr.strip())

        # Commit changes
        commit_result = subprocess.run(
            ["git", "commit", "-m", message], cwd=data_dir, capture_output=True, text=True, check=True
        )
        print(commit_result.stdout.strip())
        if commit_result.stderr:
            print(commit_result.stderr.strip())

        print("Git commit complete.")
    except subprocess.CalledProcessError as e:
        print(f"Error during Git commit: {e}")
        print(e.stdout)
        print(e.stderr)
        raise typer.Exit(code=1)
    except FileNotFoundError:
        print("Error: 'git' command not found. Please ensure Git is installed and in your PATH.")
        raise typer.Exit(code=1)
    # Removed typer.Exit(code=0)

if __name__ == "__main__":
    try:
        app()
    except typer.Exit as e:
        if e.code != 0:
            raise
