import typer
from typing import Optional
from rich.console import Console
from cocli.core.config import get_companies_dir, get_campaign
from cocli.core.prospects_csv_manager import ProspectsIndexManager
from cocli.models.companies.company import Company
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

app = typer.Typer()
console = Console()

@app.command()
def main(campaign_name: Optional[str] = typer.Argument(None, help="Campaign name. Defaults to current context.")) -> None:
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
        if not company.name or not company.slug:
            continue
            
        from cocli.core.text_utils import calculate_company_hash
        
        prospect = GoogleMapsProspect(
            place_id=company.place_id,
            name=company.name,
            domain=company.domain,
            website=company.website_url,
            full_address=company.full_address,
            street_address=company.street_address,
            city=company.city,
            state=company.state,
            zip=company.zip_code,
            country=company.country,
            phone_1=company.phone_1,
            phone_standard_format=company.phone_number,
            average_rating=company.average_rating,
            reviews_count=company.reviews_count,
            company_slug=company.slug,
            company_hash=calculate_company_hash(
                str(company.name), 
                str(company.street_address) if company.street_address else None,
                str(company.zip_code) if company.zip_code else None
            )
        )
        
        if manager.append_prospect(prospect):
            recovered_count += 1
            if recovered_count % 100 == 0:
                 console.print(f"Recovered {recovered_count} prospects...")

    console.print("\n[bold green]Recovery Complete![/bold green]")
    console.print(f"Recovered: [bold]{recovered_count}[/bold]")
    console.print(f"Already in Index: [bold]{already_exists}[/bold]")
    console.print(f"Skipped (No Place ID): [bold]{skipped_no_id}[/bold]")

if __name__ == "__main__":
    app()
