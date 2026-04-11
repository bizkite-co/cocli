from cocli.core.bootstrap import setup_environment

# Apply CUDA env and Data Home before any other imports
setup_environment()

import os
from typing import Optional
import typer
from rich.console import Console

from cocli.commands import (
    companies,
    enrich,
    query,
    audit,
    task,
    admin,
    data,
    register_commands,
)
from cocli.core.paths import paths

console = Console()
app = typer.Typer(no_args_is_help=True)


@app.callback()
def main_callback(
    campaign: Optional[str] = typer.Option(
        None,
        "--campaign",
        "-c",
        help="Override the active campaign context for this command.",
    ),
) -> None:
    if campaign:
        os.environ["COCLI_CAMPAIGN"] = campaign

    from cocli.core.environment import get_environment, Environment

    env = get_environment()
    if env != Environment.PROD:
        color = "green" if env == Environment.DEV else "yellow"
        console.print(
            f"[{color} bold]RUNNING IN {env.value.upper()} MODE[/ {color} bold]"
        )
        console.print(f"[dim]Data Root: {paths.root}[/dim]\n")


app.add_typer(enrich.app, name="enrich", help="Commands for enriching company data.")
app.add_typer(query.app, name="query", help="Commands for querying company data.")
app.add_typer(
    audit.app,
    name="audit",
    help="Auditing tools for the cocli system structure and integrity.",
)
app.add_typer(
    task.app, name="task", help="Manage development tasks and architectural issues."
)
app.add_typer(
    admin.app, name="admin", help="Administrative commands for system management."
)
app.add_typer(
    data.app,
    name="data",
    help="Utilities for interacting with frictionless data files.",
)
try:
    from cocli.commands.tui import app as tui_app

    app.add_typer(tui_app, name="tui", help="Launches the Textual TUI for cocli.")
except ImportError as e:
    console.print(f"[yellow]Textual TUI commands not available: {e}[/yellow]")

app.add_typer(companies.app, name="companies", help="Commands for managing companies.")

register_commands(app)


if __name__ == "__main__":
    app()
