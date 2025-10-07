from pathlib import Path
from typing import Optional, List
from datetime import datetime
import csv

import typer

from cocli.commands.import_data import import_data
from cocli.scrapers.google_maps import scrape_google_maps # Import the actual scraper function
from cocli.core.config import get_scraped_data_dir
from cocli.models.google_maps import GoogleMapsData

app = typer.Typer()

@app.command()
def lead_scrape(
    query: str = typer.Argument(..., help="Search query for Google Maps."),
    zip_code: Optional[str] = typer.Option(None, "--zip", "-z", help="Zip code for location-based search."),
    city: Optional[str] = typer.Option(None, "--city", "-c", help="City and State (e.g., 'Brea,CA') for location-based search."),
    cleanup: bool = typer.Option(False, "--cleanup", "-x", help="Delete the scraped CSV file after successful import."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug output for scraping and import."),
    headed: bool = typer.Option(False, "--headed", help="Launch browser in headed mode for debugging."),
):
    """
    Scrapes leads from Google Maps and imports them into the company database.
    """
    if zip_code and city:
        typer.echo("Error: Cannot provide both --zip and --city. Please choose one.", err=True)
        raise typer.Exit(code=1)

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

        scraped_data = scrape_google_maps(
            location_param=location_param,
            search_string=query,
            debug=debug,
            headless=not headed, # Use 'not headed' to launch in headed mode when --headed is true
        )

        if not scraped_data:
            typer.echo("Scraping failed, no data was returned.", err=True)
            raise typer.Exit(code=1)

        # Generate a unique filename for the CSV
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        safe_query = "".join(c if c.isalnum() else "_" for c in query)
        filename = f"google_maps_scrape_{safe_query}_{timestamp}.csv"
        
        output_dir = get_scraped_data_dir()
        output_dir.mkdir(parents=True, exist_ok=True) # Ensure directory exists
        scraped_csv_path = output_dir / filename

        # Write the scraped data to a CSV file
        with open(scraped_csv_path, "w", newline="", encoding="utf-8") as csvfile:
            fieldnames = list(GoogleMapsData.model_fields.keys())
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for item in scraped_data:
                writer.writerow(item.model_dump())

        typer.echo(f"Scraping completed. Results saved to {scraped_csv_path}")

        # Step 2: Import data
        typer.echo(f"Importing data from {scraped_csv_path}...")
        import_data(
            importer_name="google-maps",
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
