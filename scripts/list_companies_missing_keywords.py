import csv
import logging
from typing import Optional
import typer
from rich.console import Console
from rich.progress import track

from cocli.models.company import Company
from cocli.core.config import get_companies_dir
from cocli.models.website import Website
import yaml

app = typer.Typer()
console = Console()

def get_website_data(company_slug: str) -> Optional[Website]:
    """Helper to load the website.md data for a company."""
    website_md_path = get_companies_dir() / company_slug / "enrichments" / "website.md"
    if not website_md_path.exists():
        return None
    
    try:
        content = website_md_path.read_text()
        # Extract YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---")
            if len(parts) >= 3:
                data = yaml.safe_load(parts[1])
                return Website.model_validate(data)
    except Exception as e:
        logging.error(f"Error loading website data for {company_slug}: {e}")
    return None

@app.command()
def run(
    campaign: str = typer.Option("turboship", "--campaign", "-c"),
    output: str = typer.Option("companies_missing_keywords.csv", "--output", "-o")
) -> None:
    """
    Identifies companies in a campaign that have been enriched but have no found keywords.
    """
    console.print(f"Analyzing companies in campaign: [bold]{campaign}[/bold]")
    
    missing_keywords = []
    
    # We iterate through all companies. In a large dataset, we might want to filter by campaign tags.
    all_companies = list(Company.get_all())
    
    for company in track(all_companies, description="Checking companies..."):
        # Check if the company belongs to the campaign (simple tag check)
        if campaign not in company.tags:
            continue
            
        website_data = get_website_data(company.slug)
        if not website_data:
            continue # Not enriched yet
            
        if not website_data.found_keywords:
            missing_keywords.append({
                "name": company.name,
                "slug": company.slug,
                "domain": str(website_data.url),
                "tech": ", ".join(website_data.tech_stack)
            })

    if missing_keywords:
        with open(output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["name", "slug", "domain", "tech"])
            writer.writeheader()
            writer.writerows(missing_keywords)
        
        console.print(f"[green]Done![/green] Found [bold]{len(missing_keywords)}[/bold] companies missing keywords.")
        console.print(f"Results saved to: [cyan]{output}[/cyan]")
    else:
        console.print("[yellow]No companies found missing keywords (among those enriched).[/yellow]")

if __name__ == "__main__":
    app()
