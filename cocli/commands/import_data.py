import typer
from pathlib import Path
from typing import Any

from ..importers import lead_sniper # Import specific importer

app = typer.Typer()

@app.command()
def import_data(
    importer_name: str = typer.Argument(..., help="Name of the importer to use."),
    file_path: Path = typer.Argument(..., help="Path to the data file to import."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug output."),
):
    """
    Import data using a specified importer.
    """
    if not file_path.is_file():
        print(f"Error: File not found at {file_path}")
        raise typer.Exit(code=1)

    # Dynamically get the importer function from the importers module
    # This assumes importer_name matches a function name in the importers package
    try:
        # Using getattr to fetch the function from the imported module
        # For now, we only have lead_sniper, but this makes it extensible
        if importer_name == "lead-sniper":
            importer_func = lead_sniper.lead_sniper
        else:
            print(f"Error: Importer '{importer_name}' not found.")
            raise typer.Exit(code=1)

    except AttributeError:
        print(f"Error: Importer '{importer_name}' not found.")
        raise typer.Exit(code=1)

    try:
        importer_func(file_path, debug)
        print(f"Data imported successfully using '{importer_name}'.")
    except Exception as e:
        print(f"Error during import: {e}")
        raise typer.Exit(code=1)