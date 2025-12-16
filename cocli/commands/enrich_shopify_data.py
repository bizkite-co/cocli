import typer
from rich.console import Console
import yaml
import asyncio
from playwright.async_api import async_playwright

from cocli.core.config import get_scraped_data_dir, get_companies_dir
from cocli.core.text_utils import slugify
from cocli.core.utils import create_company_files
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
) -> None:
    """
    Enriches company data from a list of Shopify domains.
    """
    import pandas as pd # Lazy import
    shopify_csv_dir = get_scraped_data_dir() / "shopify_csv"
    input_path = shopify_csv_dir / input_filename
    if not input_path.exists():
        console.print(f"[bold red]Error:[/bold red] Input file not found: {input_path}")
        raise typer.Exit(code=1)

    df = pd.read_csv(input_path)
    
    companies_dir = get_companies_dir()

    async def _enrich_companies_async() -> None:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=not headed, devtools=devtools)
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
                website_data = await website_scraper.run(browser=browser, domain=domain, debug=debug)
                
                if website_data:
                    enrichment_dir = company_dir / "enrichments"
                    enrichment_dir.mkdir(exist_ok=True)
                    website_md_path = enrichment_dir / "website.md"
                    
                    with open(website_md_path, "w") as f:
                        f.write("---\n")
                        yaml.dump(website_data.model_dump(), f, sort_keys=False, default_flow_style=False, allow_unicode=True)
                        f.write("---\n")
                    
                    console.print(f"Enriched data for {company_name} and saved to {website_md_path}")
                else:
                    console.print(f"[bold yellow]Warning:[/bold yellow] No website data enriched for {company_name}")
            await browser.close()

    asyncio.run(_enrich_companies_async())