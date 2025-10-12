import typer
from pathlib import Path
from typing import Optional, Dict, List
import csv
from datetime import datetime

from ..scrapers import google_maps
from ..core.config import get_scraped_data_dir
from ..models.google_maps import GoogleMapsData
from ..core.utils import slugify

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
    max_results: int = typer.Option(
        30, "--max-results", "-n", help="Maximum number of results to scrape."
    ),
    output_dir: Path = typer.Option(
        get_scraped_data_dir(),
        "--output-dir",
        "-o",
        help="Output directory for scraped data. Defaults to the 'scraped_data' directory.",
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug output for scraping."),
) -> None:
    """
    Scrape data from Google Maps.
    """
    if not zip_code and not city:
        typer.echo("Error: Either --zip or --city must be provided.", err=True)
        raise typer.Exit(code=1)

    if zip_code and city:
        typer.echo("Error: Cannot provide both --zip and --city. Please choose one.", err=True)
        raise typer.Exit(code=1)

    location_param: Dict[str, str] = {}
    if zip_code:
        location_param["zip_code"] = zip_code
    elif city:
        location_param["city"] = city

    try:
        scraper = google_maps.scrape_google_maps(
            location_param=location_param, 
            search_strings=[query], 
            debug=debug
        )

        scraped_data: List[GoogleMapsData] = []
        for i, item in enumerate(scraper):
            if i >= max_results:
                break
            scraped_data.append(item)

        if not scraped_data:
            typer.echo("No data scraped.", err=True)
            raise typer.Exit(code=1)

        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = slugify(query) + f"-{timestamp}.csv"
        output_file = output_dir / filename

        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(scraped_data[0].model_dump().keys())
            for item in scraped_data:
                writer.writerow(item.model_dump().values())

        typer.echo(f"Scraping completed. Results saved to {output_file}")
    except Exception as e:
        typer.echo(f"Error during scraping: {e}", err=True)
        raise typer.Exit(code=1)

