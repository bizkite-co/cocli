from __future__ import annotations
from cocli.core.bootstrap import setup_environment

setup_environment()

import os
from typing import Optional
import typer
from rich.console import Console

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
    from cocli.core.paths import paths

    env = get_environment()
    if env != Environment.PROD:
        color = "green" if env == Environment.DEV else "yellow"
        console.print(
            f"[{color} bold]RUNNING IN {env.value.upper()} MODE[/ {color} bold]"
        )
        console.print(f"[dim]Data Root: {paths.root}[/dim]\n")


# Register only the worker commands, audit, and campaign rollout subcommands
from cocli.commands import worker, audit
from cocli.commands.campaign import rollout

app.add_typer(worker.app, name="worker", help="Manage background scrape/details/enrichment workers.")
app.add_typer(audit.app, name="audit", help="Auditing tools for the cocli system structure.")

# Nest campaign rollout
campaign_app = typer.Typer(no_args_is_help=True, help="Manage campaigns.")
campaign_app.add_typer(rollout.app, name="rollout", help="Campaign rollout management.")
app.add_typer(campaign_app, name="campaign")


if __name__ == "__main__":
    app()
