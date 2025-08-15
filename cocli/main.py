from pathlib import Path
import typer
from . import importers

# Create the main Typer application
app = typer.Typer()

@app.command(name="importer")
def import_data(
    format: str = typer.Argument(..., help="The name of the importer to use (e.g., 'lead-sniper')."),
    filepath: Path = typer.Argument(..., help="The path to the file to import.", file_okay=True, dir_okay=False, readable=True)
):
    """
    Imports companies from a specified file using a given format.
    """
    importer_func = getattr(importers, format.replace('-', '_'), None)

    if importer_func:
        importer_func(filepath)
    else:
        print(f"Error: Importer '{format}' not found.")
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
