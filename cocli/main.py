from .commands import companies

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

try:
    from .commands.tui import run_tui_app # New import
    @app.command(name="tui", help="Launches the Textual TUI for cocli.") # New command
    def tui_command() -> None:
        run_tui_app()
except ImportError:
    console.print("[yellow]Textual TUI commands not available. Install cocli with 'full' extra to enable.[/yellow]")
    # Optionally, provide a placeholder command or just omit it.
    # For now, we'll just omit it by not registering the command.

app.add_typer(companies.app, name="companies", help="Commands for managing companies.")

register_commands(app)




if __name__ == "__main__":
    app()
