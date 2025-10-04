
import typer
import pandas as pd
from pathlib import Path
from rich.console import Console
import yaml

from cocli.core.config import get_companies_dir
from cocli.core.utils import slugify, create_company_files
from cocli.enrichment.website_scraper import WebsiteScraper
from cocli.models.company import Company
from cocli.models.website import Website

app = typer.Typer()
console = Console()

@app.command()
def enrich_websites(
    input_path: Path = typer.Argument(..., help="Input CSV file with domains to enrich."),
    force: bool = typer.Option(False, "--force", "-f", help="Force enrichment of all companies, even if they already exist."),
    headed: bool = typer.Option(False, "--headed", help="Run the browser in headed mode."),
    devtools: bool = typer.Option(False, "--devtools", help="Open browser with devtools open."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug mode with breakpoints."),
):
    """
    Enriches company data from a list of domains in a CSV file.
    """
    if not input_path.exists():
        console.print(f"[bold red]Error:[/bold red] Input file not found: {input_path}")
        raise typer.Exit(code=1)

    df = pd.read_csv(input_path)
    
    companies_dir = get_companies_dir()

    for index, row in df.iterrows():
        domain = row.get("Domain")
        if pd.isna(domain):
            continue

        if pd.notna(row.get("Email_From_WEBSITE")):
            console.print(f"Skipping {row.get('Name')} as it already has an email.")
            continue

        company_name = row.get("Name", domain.split('.')[0].replace('-', ' ').title())
        company_slug = slugify(company_name)

        company_dir = companies_dir / company_slug
        
        company = Company.from_directory(company_dir)
        if not company:
            company = Company(name=company_name, slug=company_slug, domain=domain)
        
        if company_dir.exists() and not force:
            enrichment_dir = company_dir / "enrichments"
            website_md_path = enrichment_dir / "website.md"
            if website_md_path.exists():
                console.print(f"Skipping existing company: {company_name}")
                continue
        
        create_company_files(company, company_dir)
        
        website_scraper = WebsiteScraper()
        website_data = website_scraper.run(company, headed=headed, devtools=devtools, debug=debug)

        # Update the dataframe with the enriched data
        df.at[index, "Email_From_WEBSITE"] = website_data.email
        df.at[index, "Facebook_URL"] = website_data.facebook_url
        df.at[index, "Linkedin_URL"] = website_data.linkedin_url
        df.at[index, "Instagram_URL"] = website_data.instagram_url
        df.at[index, "Twitter_URL"] = website_data.twitter_url
        df.at[index, "Youtube_URL"] = website_data.youtube_url
        
        enrichment_dir = company_dir / "enrichments"
        enrichment_dir.mkdir(exist_ok=True)
        website_md_path = enrichment_dir / "website.md"
        
        with open(website_md_path, "w") as f:
            f.write("---\n")
            yaml.dump(website_data.model_dump(), f, sort_keys=False, default_flow_style=False, allow_unicode=True)
            f.write("---\n")
        
        console.print(f"Enriched data for {company_name} and saved to {website_md_path}")

    df.to_csv(input_path, index=False)

