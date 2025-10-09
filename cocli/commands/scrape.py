import typer
from pathlib import Path
from typing import Optional, Dict, List # Added for Optional and Dict type hints

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
        google_maps.scrape_google_maps(location_param, query, max_results=max_results, debug=debug)
        typer.echo(f"Scraping completed. Results saved to {output_dir}")
    except Exception as e:
        typer.echo(f"Error during scraping: {e}", err=True)
        raise typer.Exit(code=1)

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
        # The scrape_google_maps function in cocli.scrapers.google_maps returns a list[GoogleMapsData]
        # The command itself should return nothing or a success message.
        google_maps.scrape_google_maps(location_param, query, output_dir, debug)
        typer.echo(f"Scraping completed. Results saved to {output_dir}")
        return output_dir
    except Exception as e:
        typer.echo(f"Error during scraping: {e}", err=True)
        raise typer.Exit(code=1)
