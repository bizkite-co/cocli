import csv
from typing import Optional
import typer
from rich.console import Console
from rich.progress import track

from cocli.models.companies.company import Company
from cocli.core.config import get_companies_dir, get_campaign, get_campaign_dir
from cocli.models.companies.website import Website
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
                
                # Hotfix for legacy/malformed personnel data
                if "personnel" in data and isinstance(data["personnel"], list):
                    sanitized_personnel = []
                    for p in data["personnel"]:
                        if isinstance(p, str):
                            sanitized_personnel.append({"raw_entry": p})
                        elif isinstance(p, dict):
                            sanitized_personnel.append(p)
                    data["personnel"] = sanitized_personnel

                return Website.model_validate(data)
    except Exception:
        # logging.error(f"Error loading website data for {company_slug}: {e}")
        pass
    return None

@app.command()
def run(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c"),
    output: str = typer.Option("companies_with_keywords.csv", "--output", "-o")
) -> None:
    """
    Identifies companies in a campaign that have keyword data in any of the sources:
    - Company.keywords (List)
    - Company.meta_keywords (String)
    - Website.found_keywords (List)
    """
    if campaign is None:
        campaign = get_campaign()
    
    if campaign is None:
        campaign = "turboship"

    console.print(f"Analyzing companies in campaign: [bold]{campaign}[/bold]")
    
    campaign_dir = get_campaign_dir(campaign)
    if not campaign_dir:
        console.print(f"[red]Campaign directory not found for: {campaign}[/red]")
        raise typer.Exit(code=1)

    export_dir = campaign_dir / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    output_path = export_dir / output

    with_keywords = []
    
    # We iterate through all companies.
    all_companies = list(Company.get_all())
    
    for company in track(all_companies, description="Checking companies..."):
        # Check if the company belongs to the campaign (simple tag check)
        if campaign not in company.tags:
            continue
            
        website_data = get_website_data(company.slug)
        
        # Check all sources
        c_keywords = company.keywords or []
        c_meta = company.meta_keywords
        w_found = website_data.found_keywords if website_data else []
        
        has_keywords = False
        if c_keywords:
            has_keywords = True
        if c_meta and str(c_meta).strip() and str(c_meta).lower() != "null":
            has_keywords = True
        if w_found:
            has_keywords = True
            
        if has_keywords:
            with_keywords.append({
                "name": company.name,
                "slug": company.slug,
                "domain": str(company.domain or ""),
                "keywords": ", ".join(c_keywords),
                "meta_keywords": str(c_meta or ""),
                "found_keywords": ", ".join(w_found) if w_found else ""
            })

    if with_keywords:
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["name", "slug", "domain", "keywords", "meta_keywords", "found_keywords"])
            writer.writeheader()
            writer.writerows(with_keywords)
        
        console.print(f"[green]Done![/green] Found [bold]{len(with_keywords)}[/bold] companies with keyword data.")
        console.print(f"Results saved to: [cyan]{output_path}[/cyan]")
    else:
        console.print("[yellow]No companies found with keyword data.[/yellow]")

if __name__ == "__main__":
    app()
