import typer
import pandas as pd
from rich.console import Console
import yaml

from cocli.core.config import get_scraped_data_dir, get_companies_dir
from cocli.core.utils import slugify, create_company_files
from cocli.enrichment.website_scraper import WebsiteScraper
from cocli.models.company import Company

app = typer.Typer()
console = Console()

@app.command()
def enrich_shopify_data(
    input_filename: str = typer.Option("index.csv", "--input", "-i", help="Input CSV file with domains to enrich."),
    force: bool = typer.Option(False, "--force", "-f", help="Force enrichment of all companies, even if they already exist."),
    headed: bool = typer.Option(False, "--headed", help="Run the browser in headed mode."),
    devtools: bool = typer.Option(False, "--devtools", help="Open browser with devtools open."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug mode with breakpoints."),
):
    """
    Enriches company data from a list of Shopify domains.
    """
    shopify_csv_dir = get_scraped_data_dir() / "shopify_csv"
    input_path = shopify_csv_dir / input_filename
    if not input_path.exists():
        console.print(f"[bold red]Error:[/bold red] Input file not found: {input_path}")
        raise typer.Exit(code=1)

    df = pd.read_csv(input_path)
    
    companies_dir = get_companies_dir()

    for index, row in df.iterrows():
        domain = row["domain"]
        visits_str = row.get("visits_per_day")
        visits = None
        if pd.notna(visits_str):
            try:
                visits = int(str(visits_str).replace(',', ''))
            except (ValueError, TypeError):
                visits = None

        company_name = domain.split('.')[0].replace('-', ' ').title()
        company_slug = slugify(company_name)

        company_dir = companies_dir / company_slug
        if company_dir.exists() and not force:
            console.print(f"Skipping existing company: {company_name}")
            continue
        
        company = Company(name=company_name, slug=company_slug, domain=domain, visits_per_day=visits)
        
        company_dir = companies_dir / company_slug
        create_company_files(company, company_dir)
        
        website_scraper = WebsiteScraper()
        website_data = website_scraper.run(company, headed=headed, devtools=devtools, debug=debug)
        
        enrichment_dir = company_dir / "enrichments"
        enrichment_dir.mkdir(exist_ok=True)
        website_md_path = enrichment_dir / "website.md"
        
        with open(website_md_path, "w") as f:
            f.write("---\n")
            yaml.dump(website_data.model_dump(), f, sort_keys=False, default_flow_style=False, allow_unicode=True)
            f.write("---\n")
        
        console.print(f"Enriched data for {company_name} and saved to {website_md_path}")