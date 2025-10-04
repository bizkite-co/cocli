
import typer
import toml
from pathlib import Path

from ..scrapers.google_maps import scrape_google_maps
from ..core.config import get_scraped_data_dir

app = typer.Typer()

@app.command()
def scrape_prospects(
    campaign_name: str = typer.Argument(..., help="Name of the campaign to scrape prospects for.")
):
    """
    Scrape prospects for a campaign from Google Maps.
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
    
    for location in locations:
        for query in queries:
            print(f"Scraping '{query}' in '{location}'...")
            scrape_google_maps(
                location_param={"city": location},
                search_string=query,
                output_dir=output_dir
            )
