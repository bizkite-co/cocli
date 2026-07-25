from cocli.core.bootstrap import setup_environment

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


def _format_recursive_help(typer_app: typer.Typer, prefix: str = "cocli") -> str:
    """Recursively traverses Typer command tree and outputs plain text for grepping (rg)."""
    lines = []
    for cmd in typer_app.registered_commands:
        cmd_name = cmd.name or (cmd.callback.__name__ if cmd.callback else "")
        full_cmd = f"{prefix} {cmd_name}".strip()
        doc = (cmd.help or (cmd.callback.__doc__ if cmd.callback else "") or "").strip().split("\n")[0]
        lines.append(f"{full_cmd:<50} {doc}")

    for group in typer_app.registered_groups:
        group_name = group.name or ""
        sub_prefix = f"{prefix} {group_name}".strip()
        if group.typer_instance:
            lines.extend(_format_recursive_help(group.typer_instance, prefix=sub_prefix).split("\n"))
    return "\n".join(sorted(set(lines)))


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    campaign: Optional[str] = typer.Option(
        None,
        "--campaign",
        "-c",
        help="Override the active campaign context for this command.",
    ),
    help_text: bool = typer.Option(
        False,
        "--help-text",
        "-ht",
        help="Print recursive plain-text list of all CLI commands for grepping.",
    ),
) -> None:
    if help_text:
        print(_format_recursive_help(app))
        raise typer.Exit()

    if campaign:
        os.environ["COCLI_CAMPAIGN"] = campaign

    from cocli.core.environment import get_environment, Environment

    env = get_environment()
    if env != Environment.PROD:
        color = "green" if env == Environment.DEV else "yellow"
        console.print(
            f"[{color} bold]RUNNING IN {env.value.upper()} MODE[/{color} bold]"
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
