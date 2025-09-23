import typer
import pandas as pd
from pathlib import Path
from typing import List
from rich.console import Console

from cocli.core.config import get_scraped_data_dir

app = typer.Typer()
console = Console()

@app.command()
def process_shopify_scrapes(
    output_filename: str = typer.Option("index.csv", "--output", "-o", help="Output filename for the compiled data."),
):
    """
    Compiles and deduplicates scraped Shopify data from multiple CSV files into a single index file.
    """
    shopify_csv_dir = get_scraped_data_dir() / "shopify_csv"
    if not shopify_csv_dir.exists():
        console.print(f"[bold red]Error:[/bold red] Directory not found: {shopify_csv_dir}")
        raise typer.Exit(code=1)

    csv_files = [f for f in shopify_csv_dir.glob("*.csv") if f.name != output_filename]
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
    
    output_path = shopify_csv_dir / output_filename
    compiled_df.to_csv(output_path, index=False)
    console.print(f"Successfully compiled {len(compiled_df)} unique domains into {output_path}")
