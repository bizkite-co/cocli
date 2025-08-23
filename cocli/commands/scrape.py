import typer
from pathlib import Path

from ..scrapers import google_maps # Import specific scraper

app = typer.Typer()

@app.command()
def scrape_google_maps(
    query: str = typer.Argument(..., help="Search query for Google Maps."),
    output_file: Path = typer.Option(
        "google_maps_results.json",

        "--output",
        "-o",
        help="Output JSON file for scraped data.",
    ),
):
    """
    Scrape data from Google Maps.
    """
    try:
        google_maps.scrape(query, output_file)
        print(f"Scraping completed. Results saved to {output_file}")
    except Exception as e:
        print(f"Error during scraping: {e}")
        raise typer.Exit(code=1)