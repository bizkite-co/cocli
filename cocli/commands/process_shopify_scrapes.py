import typer
import pandas as pd
from pathlib import Path
from typing import List
from rich.console import Console

from cocli.core.config import get_scraped_data_dir, get_companies_dir
from cocli.models.company import Company
from cocli.core.utils import create_company_files, slugify

app = typer.Typer()
console = Console()

@app.command()
def process_shopify_scrapes():
    """
    Compiles and deduplicates scraped Shopify data from multiple CSV files into a single index file.
    """
    shopify_csv_dir = get_scraped_data_dir() / "shopify_csv"
    if not shopify_csv_dir.exists():
        console.print(f"[bold red]Error:[/bold red] Directory not found: {shopify_csv_dir}")
        raise typer.Exit(code=1)

    csv_files = [f for f in shopify_csv_dir.glob("*.csv") if f.name != 'index.csv']
    if not csv_files:
        console.print("[bold yellow]Warning:[/bold yellow] No CSV files found to process.")
        raise typer.Exit()

    all_data = []
    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)
            # Clean up the Website column
            df["domain"] = df["Website"].apply(lambda x: x.split('/')[-1])
            df = df.rename(columns={"Popularity_Visitors_Per_Day": "visits_per_day", "Scrape_Date": "scraped_date"})
            all_data.append(df[["domain", "visits_per_day", "scraped_date"]])
        except Exception as e:
            console.print(f"[bold yellow]Warning:[/bold yellow] Could not process file {csv_file.name}: {e}")

    if not all_data:
        console.print("[bold red]Error:[/bold red] No data could be processed from the CSV files.")
        raise typer.Exit(code=1)

    compiled_df = pd.concat(all_data, ignore_index=True)
    compiled_df = compiled_df.drop_duplicates(subset=["domain"], keep="last")

    companies_dir = get_companies_dir()
    if not companies_dir.exists():
        console.print(f"[bold red]Error:[/bold red] Companies directory not found: {companies_dir}")
        raise typer.Exit(code=1)

    # NOTE: This loads all companies into memory. For a very large number of
    # companies, this could be memory-intensive. A future optimization could be
    # to partition the data (e.g., by first letter of the domain) or use a
    # lightweight database for lookups.
    companies_by_domain = {}
    for company_dir in companies_dir.iterdir():
        if company_dir.is_dir():
            company = Company.from_directory(company_dir)
            if company and company.domain:
                companies_by_domain[company.domain] = (company, company_dir)

    updated_companies = 0
    for index, row in compiled_df.iterrows():
        domain = row["domain"]
        visits = row["visits_per_day"]

        if domain in companies_by_domain:
            company, company_dir = companies_by_domain[domain]
            console.print(f"Updating {company.name} with {visits} visits per day.")
            company.visits_per_day = int(str(visits).replace(',', ''))
            create_company_files(company, company_dir)
            updated_companies += 1
        else:
            console.print(f"[yellow]Warning:[/yellow] No company found with domain: {domain}")

    console.print(f"Successfully updated {updated_companies} companies.")
