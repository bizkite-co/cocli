import typer
import yaml
from pathlib import Path
from typing import Optional
from rich.console import Console
from cocli.core.config import get_companies_dir, get_campaign
from cocli.core.prospects_csv_manager import ProspectsIndexManager
from cocli.core.text_utils import slugify
from cocli.models.company import Company
from cocli.models.google_maps_prospect import GoogleMapsProspect

app = typer.Typer()
console = Console()

@app.command()
def main(campaign_name: Optional[str] = typer.Argument(None, help="Campaign name. Defaults to current context.")):
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified and no active context.[/bold red]")
        raise typer.Exit(1)

    companies_dir = get_companies_dir()
    manager = ProspectsIndexManager(campaign_name)
    
    console.print(f"Recovering prospect index for campaign: [bold cyan]{campaign_name}[/bold cyan]...")

    recovered_count = 0
    already_exists = 0
    skipped_no_id = 0

    # Iterate all companies
    company_paths = [p for p in companies_dir.iterdir() if p.is_dir()]
    
    for company_path in company_paths:
        # Check if tagged
        tags_path = company_path / "tags.lst"
        if not tags_path.exists():
            continue
            
        try:
            tags = tags_path.read_text().strip().splitlines()
            if campaign_name not in tags:
                continue
        except Exception:
            continue
            
        # Load company data
        company = Company.from_directory(company_path)
        if not company or not company.place_id:
            skipped_no_id += 1
            continue
            
        # Check index
        if manager.has_place_id(company.place_id):
            already_exists += 1
            continue
            
        # Reconstruct prospect
        # We try to map Company fields back to GoogleMapsProspect
        prospect = GoogleMapsProspect(
            Place_ID=company.place_id,
            Name=company.name,
            Domain=company.domain,
            Website=company.website_url,
            Full_Address=company.full_address,
            Street_Address=company.street_address,
            City=company.city,
            State=company.state,
            Zip=company.zip_code,
            Country=company.country,
            Phone_1=company.phone_1,
            Phone_Standard_format=company.phone_number,
            Average_rating=company.average_rating,
            Reviews_count=company.reviews_count,
            company_slug=company.slug
        )
        
        if manager.append_prospect(prospect):
            recovered_count += 1
            if recovered_count % 100 == 0:
                 console.print(f"Recovered {recovered_count} prospects...")

    console.print(f"\n[bold green]Recovery Complete![/bold green]")
    console.print(f"Recovered: [bold]{recovered_count}[/bold]")
    console.print(f"Already in Index: [bold]{already_exists}[/bold]")
    console.print(f"Skipped (No Place ID): [bold]{skipped_no_id}[/bold]")

if __name__ == "__main__":
    app()
