from pathlib import Path
from typing import Optional

import typer

from cocli.commands.import_data import import_data
from cocli.scrapers.google_maps import scrape_google_maps # Import the actual scraper function
from cocli.core.config import get_scraped_data_dir

app = typer.Typer()

@app.command()
def lead_scrape(
    query: str = typer.Argument(..., help="Search query for Google Maps."),
    zip_code: Optional[str] = typer.Option(None, "--zip", "-z", help="Zip code for location-based search."),
    city: Optional[str] = typer.Option(None, "--city", "-c", help="City and State (e.g., 'Brea,CA') for location-based search."),
    cleanup: bool = typer.Option(False, "--cleanup", "-x", help="Delete the scraped CSV file after successful import."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug output for scraping and import."),
):
    """
    Scrapes leads from Google Maps and imports them into the company database.
    """
    typer.echo(f"Starting lead scrape for query: '{query}'")

    scraped_csv_path: Optional[Path] = None
    try:
        # Step 1: Scrape Google Maps
        typer.echo("Scraping Google Maps...")
        location_param = {}
        if zip_code:
            location_param["zip_code"] = zip_code
        elif city:
            location_param["city"] = city
        else:
            typer.echo("Error: Either --zip or --city must be provided.", err=True)
            raise typer.Exit(code=1)

        scraped_csv_path = scrape_google_maps(
            location_param=location_param,
            search_string=query,
            output_dir=get_scraped_data_dir(),
            debug=debug,
        )
        if scraped_csv_path is None:
            typer.echo("Scraping failed, no CSV file was generated.", err=True)
            raise typer.Exit(code=1)

        typer.echo(f"Scraping completed. Results saved to {scraped_csv_path}")

        # Step 2: Import data
        typer.echo(f"Importing data from {scraped_csv_path}...")
        import_data(
            importer_name="lead-sniper",
            file_path=scraped_csv_path,
            debug=debug,
        )
        typer.echo("Data import completed successfully.")

    except typer.Exit as e:
        # Re-raise TyperExit exceptions to propagate specific error codes and messages
        raise e
    except Exception as e:
        typer.echo(f"An unexpected error occurred during lead scrape: {e}", err=True)
        raise typer.Exit(code=1)
    finally:
        # Step 3: Cleanup
        if cleanup and scraped_csv_path and scraped_csv_path.exists():
            typer.echo(f"Cleaning up scraped CSV file: {scraped_csv_path}")
            scraped_csv_path.unlink()
            typer.echo("Scraped CSV file deleted.")
