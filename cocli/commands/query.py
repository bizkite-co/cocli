import typer
from typing import Optional, List
from geopy.distance import geodesic # type: ignore
import logging
from rich.console import Console

from ..core.config import get_companies_dir, get_campaign
from ..core.geocoding import get_coordinates_from_city_state
from ..models.person import Person
import yaml

logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer()

def get_enriched_emails(domain_to_slug_map: dict[str, str], domain: str) -> List[str]:
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
            from ..core.text_utils import parse_frontmatter
            frontmatter_str = parse_frontmatter(content)
            if frontmatter_str:
                frontmatter = yaml.safe_load(frontmatter_str)
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

def build_domain_to_slug_map() -> dict[str, str]:
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
                from ..core.text_utils import parse_frontmatter
                frontmatter_str = parse_frontmatter(content)
                if frontmatter_str:
                    frontmatter = yaml.safe_load(frontmatter_str)
                    domain = frontmatter.get("domain")
                    if domain:
                        domain_map[domain] = company_dir.name
            except (yaml.YAMLError, IndexError):
                continue # Skip malformed files
    return domain_map

def get_tags_for_domain(domain_to_tags_map: dict[str, List[str]], domain: str) -> List[str]:
    return domain_to_tags_map.get(domain, [])

def build_domain_to_tags_map() -> dict[str, List[str]]:
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
                from ..core.text_utils import parse_frontmatter
                frontmatter_str = parse_frontmatter(content)
                if frontmatter_str:
                    frontmatter = yaml.safe_load(frontmatter_str)
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
def query_prospects_location(
    city: str = typer.Argument(..., help="The city to search around (e.g., 'New York, NY')."),
    radius: float = typer.Option(50.0, "--radius", "-r", help="Radius in miles to search."),
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name. Defaults to current context.")
) -> None:
    """
    Find prospects within a certain radius of a city, using the prospects CSV for speed.
    This avoids iterating through thousands of individual company files.
    """
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified and no current context set.[/bold red]")
        raise typer.Exit(1)

    # 1. Geocode the input city
    console.print(f"[dim]Geocoding '{city}'...[/dim]")
    origin_coords = get_coordinates_from_city_state(city)
    if not origin_coords:
        console.print(f"[bold red]Could not geocode '{city}'. Please use 'City, ST' format.[/bold red]")
        raise typer.Exit(1)
    
    origin_point = (origin_coords["latitude"], origin_coords["longitude"])
    console.print(f"[dim]Origin: {origin_point}[/dim]")

    # 2. Load prospects from index
    from ..core.prospects_csv_manager import ProspectsIndexManager
    manager = ProspectsIndexManager(campaign_name)
    
    if not manager.index_dir.exists():
        console.print(f"[bold red]Prospects index not found at: {manager.index_dir}[/bold red]")
        raise typer.Exit(1)

    console.print(f"[dim]Reading prospects from {manager.index_dir}...[/dim]")
    
    matches = []
    prospects = manager.read_all_prospects()

    for prospect in prospects:
        if prospect.latitude is None or prospect.longitude is None:
            continue
            
        point = (prospect.latitude, prospect.longitude)
        distance = geodesic(origin_point, point).miles
        
        if distance <= radius:
            matches.append((prospect, round(distance, 1)))

    # 3. Sort by distance
    matches.sort(key=lambda x: x[1])

    # 4. Display results
    if not matches:
        console.print(f"[yellow]No prospects found within {radius} miles of {city}.[/yellow]")
        return

    console.print(f"[bold green]Found {len(matches)} prospects within {radius} miles of {city}:[/bold green]")
    
    # Print simple table
    # ID/Name | City, State | Distance
    print(f"{'Name':<40} | {'City, State':<30} | {'Distance':<10} | {'Phone':<15} | {'Website'}")
    print("-" * 120)
    
    for prospect, dist_val in matches:
        name = (prospect.name or "")[:38]
        city_state = f"{prospect.city or ''}, {prospect.state or ''}"
        dist = f"{dist_val} mi"
        phone = prospect.phone_1 or ""
        website = prospect.website or ""
        print(f"{name:<40} | {city_state:<30} | {dist:<10} | {phone:<15} | {website}")

if __name__ == "__main__":
    app()
