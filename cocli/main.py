from cocli.commands import companies

import typer

from cocli.commands import enrich
from cocli.commands import query
from cocli.commands import audit
from cocli.commands import task # Add this
from cocli.commands import admin
from cocli.core.paths import paths
from rich.console import Console

from cocli.commands import register_commands

console = Console()

app = typer.Typer(no_args_is_help=True)

@app.callback()
def main_callback() -> None:
    from cocli.core.environment import get_environment, Environment
    env = get_environment()
    if env != Environment.PROD:
        color = "green" if env == Environment.DEV else "yellow"
        console.print(f"[{color} bold]RUNNING IN {env.value.upper()} MODE[/ {color} bold]")
        console.print(f"[dim]Data Root: {paths.root}[/dim]\n")

app.add_typer(enrich.app, name="enrich", help="Commands for enriching company data.")
app.add_typer(query.app, name="query", help="Commands for querying company data.")
app.add_typer(audit.app, name="audit", help="Auditing tools for the cocli system structure and integrity.")
app.add_typer(task.app, name="task", help="Manage development tasks and architectural issues.") # Add this
app.add_typer(admin.app, name="admin", help="Administrative commands for system management.")
try:
    from cocli.commands.tui import app as tui_app # Use the app (Typer instance)
    app.add_typer(tui_app, name="tui", help="Launches the Textual TUI for cocli.")
except ImportError as e:
    console.print(f"[yellow]Textual TUI commands not available: {e}[/yellow]")

app.add_typer(companies.app, name="companies", help="Commands for managing companies.")

register_commands(app)




if __name__ == "__main__":
    app()
