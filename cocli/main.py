from cocli.commands import companies

import typer

from cocli.commands import enrich
from cocli.commands import query
from rich.console import Console

from cocli.commands import register_commands

console = Console()

app = typer.Typer(no_args_is_help=True)
app.add_typer(enrich.app, name="enrich", help="Commands for enriching company data.")
app.add_typer(query.app, name="query", help="Commands for querying company data.")

try:
    from cocli.commands.tui import run_tui_app # New import
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
