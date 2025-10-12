import typer
from typing import Optional, List
from rich.console import Console
from rich.table import Table
from pathlib import Path
import logging
import csv
from geopy.distance import geodesic # type: ignore

from ..core.config import get_companies_dir, get_scraped_data_dir, get_cocli_base_dir
from ..core.geocoding import get_coordinates_from_city_state
from ..core.utils import slugify
from ..models.company import Company
from ..models.person import Person
import yaml

def get_enriched_emails(domain_to_slug_map: dict, domain: str) -> List[str]:
    """Looks up a company by domain and returns all associated emails."""
    slug = domain_to_slug_map.get(domain)
    if not slug:
        return []

    emails = set()
    company_dir = get_companies_dir() / slug

    # 1. Get company email from _index.md
    index_file = company_dir / "_index.md"
    if index_file.exists():
        try:
            content = index_file.read_text()
            if content.startswith("---"):
                frontmatter = yaml.safe_load(content.split("---")[1])
                company_email = frontmatter.get("email")
                if company_email:
                    emails.add(company_email)
        except (yaml.YAMLError, IndexError):
            pass # Ignore malformed files

    # 2. Get contact emails from contacts/
    contacts_dir = company_dir / "contacts"
    if contacts_dir.exists():
        for contact_link in contacts_dir.iterdir():
            if contact_link.is_symlink() and contact_link.is_dir():
                person = Person.from_directory(contact_link.resolve())
                if person and person.email:
                    emails.add(person.email)
    
    return sorted(list(emails))

def build_domain_to_slug_map() -> dict:
    """Builds a lookup map from domain to a company's slug (directory name)."""
    domain_map = {}
    companies_dir = get_companies_dir()
    for company_dir in companies_dir.iterdir():
        if not company_dir.is_dir():
            continue
        
        index_file = company_dir / "_index.md"
        if index_file.exists():
            try:
                content = index_file.read_text()
                if content.startswith("---"):
                    frontmatter = yaml.safe_load(content.split("---")[1])
                    domain = frontmatter.get("domain")
                    if domain:
                        domain_map[domain] = company_dir.name
            except (yaml.YAMLError, IndexError):
                continue # Skip malformed files
    return domain_map

app = typer.Typer()
console = Console()
logger = logging.getLogger(__name__)

def get_prospects_csv_path() -> Path:
    # Assuming a single campaign context for now, this could be made dynamic
    # based on the user's current campaign context.
    return get_scraped_data_dir() / "turboship" / "prospects" / "prospects.csv"

def get_tags_for_domain(domain_to_tags_map: dict, domain: str) -> List[str]:
    return domain_to_tags_map.get(domain, [])

def build_domain_to_tags_map() -> dict:
    """Builds a lookup map from domain to a list of tags."""
    domain_map = {}
    companies_dir = get_companies_dir()
    for company_dir in companies_dir.iterdir():
        if not company_dir.is_dir():
            continue
        
        index_file = company_dir / "_index.md"
        tags_file = company_dir / "tags.lst"
        
        domain = None
        if index_file.exists():
            try:
                content = index_file.read_text()
                if content.startswith("---"):
                    frontmatter = yaml.safe_load(content.split("---")[1])
                    domain = frontmatter.get("domain")
            except (yaml.YAMLError, IndexError):
                continue # Skip malformed files
        
        if not domain:
            continue

        tags = []
        if tags_file.exists():
            tags = [tag for tag in tags_file.read_text().strip().split('\n') if tag]
        
        domain_map[domain] = tags
    return domain_map





@app.command()
def prospects(
    city: str = typer.Option(..., "--city", help="City to search in."),
    state: str = typer.Option(..., "--state", help="State to search in."),
    radius: int = typer.Option(50, "--radius", help="Search radius in miles."),
    has_email: Optional[bool] = typer.Option(None, "--has-email/--no-email", help="Filter by email presence. Default is to include all."),
):
    """
    Find prospects within a certain radius of a city, using the prospects CSV for speed.
    """
    console.print(f"Searching for prospects in {city}, {state} within a {radius}-mile radius...")

    # 1. Get target coordinates
    target_coords = get_coordinates_from_city_state(f"{city},{state}")
    if not target_coords:
        console.print(f"[bold red]Could not find coordinates for {city}, {state}.[/bold red]")
        raise typer.Exit(code=1)
    
    target_lat_lon = (target_coords['latitude'], target_coords['longitude'])

    # 2. Build lookup maps for efficient lookup
    console.print("[dim]Building domain lookup maps...[/dim]")
    domain_to_tags = build_domain_to_tags_map()
    domain_to_slug = build_domain_to_slug_map()

    # 3. Iterate through the fast prospects.csv to get location-based matches
    prospects_csv_path = get_prospects_csv_path()
    if not prospects_csv_path.exists():
        console.print(f"[bold red]Prospects CSV not found at: {prospects_csv_path}[/bold red]")
        raise typer.Exit(code=1)

    console.print(f"[dim]Reading prospects from {prospects_csv_path}...[/dim]")
    
    location_matches = []
    with open(prospects_csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # A. Filter by tag
            domain = row.get("Domain")
            if not domain:
                continue
            
            tags = get_tags_for_domain(domain_to_tags, domain)
            if "prospect" not in tags:
                continue

            # B. Filter by radius
            try:
                lat = float(row.get("Latitude", 0))
                lon = float(row.get("Longitude", 0))
                if lat == 0 or lon == 0:
                    continue
            except (ValueError, TypeError):
                continue

            distance = geodesic(target_lat_lon, (lat, lon)).miles
            if distance > radius:
                continue
            
            location_matches.append(row)

    # 4. Process matches for enrichment and final filtering
    final_prospects = []
    for prospect in location_matches:
        domain = prospect.get("Domain")
        enriched_emails = get_enriched_emails(domain_to_slug, domain) if domain else []
        
        # Apply email filter now that we have the correct data
        if has_email is not None:
            email_found = bool(enriched_emails)
            if has_email and not email_found:
                continue
            if not has_email and email_found:
                continue
        
        final_prospects.append({
            "Name": prospect.get("Name", ""),
            "Full_Address": prospect.get("Full_Address", ""),
            "Phone": prospect.get("Phone_1", ""),
            "Emails": ", ".join(enriched_emails),
        })

    # 5. Save results to CSV
    output_dir = get_cocli_base_dir() / "campaigns" / "turboship" / "prospects" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = slugify(f"{city}-{state}-{radius}mi-radius-prospects") + ".csv"
    output_path = output_dir / filename

    if final_prospects:
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ["Name", "Full_Address", "Phone", "Emails"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(final_prospects)

    console.print(f"Found {len(final_prospects)} prospects. Results saved to: {output_path}")

