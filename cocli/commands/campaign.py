
import typer
import toml
import csv
from pathlib import Path
from typing import List

from ..scrapers.google_maps import scrape_google_maps
from ..core.config import get_scraped_data_dir
from ..models.google_maps import GoogleMapsData

app = typer.Typer()

@app.command()
def scrape_prospects(
    campaign_name: str = typer.Argument(..., help="Name of the campaign to scrape prospects for."),
    force_refresh: bool = typer.Option(False, "--force-refresh", help="Force re-scraping even if fresh data is in the cache."),
    ttl_days: int = typer.Option(30, "--ttl-days", help="Time-to-live for cached data in days.")
):
    """
    Scrape prospects for a campaign from Google Maps, using a cache-first strategy.
    """
    
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
