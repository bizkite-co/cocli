import typer
from pathlib import Path
from typing import Optional # Import Optional
import logging

from ..importers import google_maps # Import specific importer
from ..core.config import get_scraped_data_dir # Import get_scraped_data_dir

logger = logging.getLogger(__name__)

app = typer.Typer()

@app.command()
def import_data(
    importer_name: str = typer.Argument(..., help="Name of the importer to use."),
    file_path: Optional[Path] = typer.Argument(None, help="Path to the data file to import. If not provided, a list of available files will be shown."), # Make file_path optional
    debug: bool = typer.Option(False, "--debug", help="Enable debug output."),
):
    """
    Import data using a specified importer.
    """
    if file_path is None:
        scraped_data_dir = get_scraped_data_dir()
        available_files = [f for f in scraped_data_dir.iterdir() if f.is_file()]

        if not available_files:
            logger.error(f"Error: No scraped data files found in {scraped_data_dir}")
            raise typer.Exit(code=1)

        logger.info("Available scraped data files:")
        for i, f in enumerate(available_files):
            logger.info(f"{i+1}. {f.name}")

        while True:
            try:
                selection = typer.prompt("Select a file by number or type the full path")
                if selection.isdigit():
                    index = int(selection) - 1
                    if 0 <= index < len(available_files):
                        file_path = available_files[index]
                        break
                    else:
                        logger.warning("Invalid number. Please try again.")
                else:
                    file_path = Path(selection)
                    if file_path.is_file():
                        break
                    else:
                        logger.error(f"Error: File not found at {file_path}. Please try again.")
            except Exception as e:
                logger.error(f"An error occurred during selection: {e}")
                logger.info("Please try again.")

    if not file_path.is_file():
        logger.error(f"Error: File not found at {file_path}")
        raise typer.Exit(code=1)

    # Dynamically get the importer function from the importers module
    # This assumes importer_name matches a function name in the importers package
    try:
        # Using getattr to fetch the function from the imported module
        # For now, we only have lead_sniper, but this makes it extensible
        if importer_name == "google-maps":
            importer_func = google_maps.google_maps
        else:
            logger.error(f"Error: Importer '{importer_name}' not found.")
            raise typer.Exit(code=1)

    except AttributeError:
        logger.error(f"Error: Importer '{importer_name}' not found.")
        raise typer.Exit(code=1)

    try:
        importer_func(file_path, debug)
        logger.info(f"Data imported successfully using '{importer_name}'.")
    except Exception as e:
        logger.error(f"Error during import: {e}")
        raise typer.Exit(code=1)