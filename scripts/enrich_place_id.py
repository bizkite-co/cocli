import typer
import yaml
import logging
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.progress import track
from cocli.core.config import get_companies_dir, get_campaign
from cocli.models.company import Company
from cocli.scrapers.google_maps_finder import find_business_on_google_maps
from cocli.core.utils import create_company_files

app = typer.Typer()
console = Console()

# Silence verbose scrapers
logging.getLogger("cocli.scrapers").setLevel(logging.WARNING)
logging.getLogger("playwright").setLevel(logging.WARNING)

@app.command()
def main(
    campaign_name: Optional[str] = typer.Argument(None, help="Campaign name. Defaults to current context."),
    limit: int = typer.Option(0, "--limit", "-l", help="Limit the number of companies to enrich (0 for no limit)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be enriched without actually doing it.")
):
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified and no active context.[/bold red]")
        raise typer.Exit(1)

    companies_dir = get_companies_dir()
    
    console.print(f"Enriching Place IDs for campaign: [bold cyan]{campaign_name}[/bold cyan]...")

    # Find companies missing place_id
    targets = []
    for company_dir in companies_dir.iterdir():
        if not company_dir.is_dir():
            continue
            
        tags_path = company_dir / "tags.lst"
        if not tags_path.exists():
            continue
            
        try:
            tags = tags_path.read_text().strip().splitlines()
            if campaign_name not in tags:
                continue
        except Exception:
            continue
            
        company = Company.from_directory(company_dir)
        if company and not company.place_id:
            # We need an address or city to search effectively
            if company.name and (company.full_address or (company.city and company.state)):
                targets.append(company)

    if not targets:
        console.print("[green]No companies missing Place IDs found for this campaign.[/green]")
        return

    console.print(f"Found [bold]{len(targets)}[/bold] companies missing Place IDs.")
    
    if limit > 0:
        targets = targets[:limit]
        console.print(f"Limiting to first [bold]{limit}[/bold] companies.")

    enriched_count = 0
    
    for company in track(targets, description="Searching Google Maps..."):
        # Strategy 1: Name + Address/City
        location_param = {}
        if company.full_address:
            location_param["address"] = company.full_address
        elif company.city and company.state:
            location_param["city"] = f"{company.city}, {company.state}"
        
        found = False
        
        # We search Google Maps by name
        try:
            result = find_business_on_google_maps(company.name, location_param)
            if result and result.get("Place_ID"):
                new_place_id = result["Place_ID"]
                console.print(f"  [green]✓[/green] Found Place ID for [bold]{company.name}[/bold] ({company.slug}): {new_place_id}")
                found = True
            
            # Strategy 2: Fallback to Domain if name search failed
            if not found and company.domain:
                # console.print(f"  [dim]Retrying with domain: {company.domain}[/dim]")
                result = find_business_on_google_maps(company.domain, location_param)
                if result and result.get("Place_ID"):
                    new_place_id = result["Place_ID"]
                    console.print(f"  [green]✓[/green] Found Place ID via domain for [bold]{company.name}[/bold] ({company.slug}): {new_place_id}")
                    found = True

            if found and result:
                if not dry_run:
                    company.place_id = result["Place_ID"]
                    company_dir = companies_dir / company.slug
                    create_company_files(company, company_dir)
                    enriched_count += 1
        except Exception as e:
            console.print(f"  [red]Error searching for {company.name} ({company.slug}): {e}[/red]")

    console.print(f"\n[bold green]Enrichment Complete![/bold green]")
    console.print(f"Enriched: [bold]{enriched_count}[/bold]")
    if dry_run:
        console.print("[yellow]Dry run: No files were actually modified.[/yellow]")

if __name__ == "__main__":
    app()
