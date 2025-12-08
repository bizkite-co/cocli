from .commands import companies
from .commands.tui import run_tui_app # New import

import logging
import typer

from .commands import enrich
from .commands import query
from rich.console import Console

from .commands import register_commands

logging.basicConfig(level=logging.DEBUG)

console = Console()

app = typer.Typer(no_args_is_help=True)
app.add_typer(enrich.app, name="enrich", help="Commands for enriching company data.")
app.add_typer(query.app, name="query", help="Commands for querying company data.")

@app.command(name="tui", help="Launches the Textual TUI for cocli.") # New command
def tui_command() -> None:
    run_tui_app()

app.add_typer(companies.app, name="companies", help="Commands for managing companies.")

register_commands(app)



if __name__ == "__main__":
    app()
