
import typer
import toml
import csv
from pathlib import Path
from typing import List, Dict, Optional

from ..scrapers.google_maps import scrape_google_maps
from ..core.config import get_scraped_data_dir
from ..models.google_maps import GoogleMapsData
from ..core.config import get_campaign, set_campaign
from rich.console import Console

app = typer.Typer(no_args_is_help=True)
console = Console()

@app.command()
def set(campaign_name: str = typer.Argument(..., help="The name of the campaign to set as the current context.")):
    """
    Sets the current campaign context.
    """
    set_campaign(campaign_name)
    console.print(f"[green]Campaign context set to:[/] [bold]{campaign_name}[/]")

@app.command()
def unset():
    """
    Clears the current campaign context.
    """
    set_campaign(None)
    console.print("[green]Campaign context cleared.[/]")

@app.command()
def show():
    """
    Displays the current campaign context.
    """
    campaign_name = get_campaign()
    if campaign_name:
        console.print(f"Current campaign context is: [bold]{campaign_name}[/]")
    else:
        console.print("No campaign context is set.")

@app.command()
def scrape_prospects(
    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign to scrape prospects for. If not provided, uses the current campaign context."),
    force_refresh: bool = typer.Option(False, "--force-refresh", help="Force re-scraping even if fresh data is in the cache."),
    ttl_days: int = typer.Option(30, "--ttl-days", help="Time-to-live for cached data in days.")
):
    """
    Scrape prospects for a campaign from Google Maps, using a cache-first strategy.
    """
    if campaign_name is None:
        campaign_name = get_campaign()
        if campaign_name is None:
            print("Error: No campaign name provided and no campaign context is set. Please provide a campaign name or set a campaign context using 'cocli campaign set <campaign_name>'.")
            raise typer.Exit(code=1)
    
    campaign_dirs = list(Path("campaigns").glob(f"**/{campaign_name}"))
    if not campaign_dirs:
        print(f"Campaign '{campaign_name}' not found.")
        raise typer.Exit(code=1)
    campaign_dir = campaign_dirs[0]
    config_path = campaign_dir / "config.toml"
    
    if not config_path.exists():
        print(f"Configuration file not found for campaign '{campaign_name}'.")
        raise typer.Exit(code=1)
        
    with open(config_path, "r") as f:
        config = toml.load(f)
        
    prospecting_config = config.get("prospecting", {})
    locations = prospecting_config.get("locations", [])
    queries = prospecting_config.get("queries", [])
    
    if not locations or not queries:
        print("No locations or queries found in the prospecting configuration.")
        raise typer.Exit(code=1)
        
    output_dir = get_scraped_data_dir() / campaign_name / "prospects"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_filepath = output_dir / "prospects.csv"

    all_prospects: Dict[str, GoogleMapsData] = {}

    # Load existing prospects to avoid duplicates in the final list
    if output_filepath.exists():
        with open(output_filepath, "r", newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if row.get("Place_ID"):
                    # Re-create the model to ensure data consistency
                    model_data = {k: v for k, v in row.items() if k in GoogleMapsData.model_fields}
                    all_prospects[row["Place_ID"]] = GoogleMapsData(**model_data)

    for location in locations:
        for query in queries:
            print(f"Scraping '{query}' in '{location}'...")
            scraped_data: List[GoogleMapsData] = scrape_google_maps(
                location_param={"city": location},
                search_string=query,
                force_refresh=force_refresh,
                ttl_days=ttl_days
            )

            for item in scraped_data:
                if item.Place_ID:
                    all_prospects[item.Place_ID] = item

    # Write all prospects (including old and new) to the CSV file
    with open(output_filepath, "w", newline="", encoding="utf-8") as csvfile:
        headers = GoogleMapsData.model_fields.keys()
        writer = csv.DictWriter(csvfile, fieldnames=headers)
        writer.writeheader()
        for item in all_prospects.values():
            writer.writerow(item.model_dump())
    
    print(f"Prospecting complete. Results saved to {output_filepath}")
