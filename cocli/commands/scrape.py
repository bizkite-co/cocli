import typer
from pathlib import Path
from typing import Optional # Added for Optional type hint

from ..scrapers import google_maps # Import specific scraper
from ..core.config import get_scraped_data_dir # Import the new function

app = typer.Typer()

@app.command()
def scrape_google_maps(
    query: str = typer.Argument(..., help="Search query for Google Maps."),
    zip_code: Optional[str] = typer.Option(
        None, "--zip", "-z", help="Zip code for location-based search."
    ),
    city: Optional[str] = typer.Option(
        None, "--city", "-c", help="City and State (e.g., 'Brea,CA') for location-based search."
    ),
    output_dir: Path = typer.Option(
        get_scraped_data_dir(),
        "--output-dir",
        "-o",
        help="Output directory for scraped data. Defaults to the 'scraped_data' directory.",
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug output for scraping."),
) -> Path:
    """
    Scrape data from Google Maps.
    """
    if not zip_code and not city:
        print("Error: Either --zip or --city must be provided.")
        raise typer.Exit(code=1)

    if zip_code and city:
        print("Error: Cannot provide both --zip and --city. Please choose one.")
        raise typer.Exit(code=1)

    location_param = {"zip_code": zip_code} if zip_code else {"city": city}

    try:
        csv_file_path = google_maps.scrape_google_maps(location_param, query, output_dir, debug)
        print(f"Scraping completed. Results saved to {csv_file_path}")
        return csv_file_path
    except Exception as e:
        print(f"Error during scraping: {e}")
        raise typer.Exit(code=1)
