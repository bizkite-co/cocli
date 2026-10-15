"""Commands for one campaign's initiatives directory."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from playwright.sync_api import Error as PlaywrightError

from cocli.application.initiative_demo import record_initiative_demo
from cocli.core.config import get_campaign, get_campaign_dir

app = typer.Typer(help="Campaign initiatives.", no_args_is_help=True)


@app.command("record-demo")
def record_demo(
    initiative: str = typer.Argument(..., help="Initiative folder under campaigns/<campaign>/initiatives/."),
    scenario: str = typer.Argument(..., help="Scenario folder under that initiative's scenarios/."),
    campaign: Optional[str] = typer.Option(
        None,
        "--campaign",
        "-c",
        help="Campaign name. Defaults to the active campaign.",
    ),
    fixture: Optional[Path] = typer.Option(
        None,
        "--fixture",
        help="Local HTML file. Skips login and does not open the live app.",
    ),
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        help="Output directory. Defaults to scenarios/<scenario>/demo/.",
    ),
    url: str = typer.Option(
        "https://roadmappartners.net/roadmap/login.html",
        help="App login URL.",
    ),
    username: str = typer.Option("appdev", help="Login name."),
    password: str = typer.Option("", help="Login password. Defaults to 1Password."),
    client_name: str = typer.Option("", help="Client to select. Defaults to the scenario's name."),
    headed: bool = typer.Option(False, "--headed", help="Show the browser window."),
    char_delay: Optional[int] = typer.Option(None, help="Milliseconds between keystrokes."),
    pause: Optional[int] = typer.Option(None, help="Milliseconds between fields."),
    pan: Optional[int] = typer.Option(None, help="Milliseconds for each camera move."),
) -> None:
    """Type a scenario into the initiative form and record the viewport."""
    campaign_name = campaign or get_campaign()
    if not campaign_name:
        typer.echo("No campaign selected. Pass --campaign or set the active campaign.")
        raise typer.Exit(1)
    campaign_dir = get_campaign_dir(campaign_name)
    if campaign_dir is None:
        typer.echo(f"Campaign directory not found: {campaign_name}")
        raise typer.Exit(1)
    initiative_dir = campaign_dir / "initiatives" / initiative
    if not initiative_dir.is_dir():
        typer.echo(f"Initiative directory not found: {initiative_dir}")
        raise typer.Exit(1)
    try:
        destination = record_initiative_demo(
            initiative_dir,
            scenario,
            fixture=fixture,
            out_dir=out,
            url=url,
            username=username,
            password=password,
            client_name=client_name,
            headed=headed,
            char_delay=char_delay,
            pause_ms=pause,
            pan_ms=pan,
        )
    except (OSError, RuntimeError, KeyError, ValueError, PlaywrightError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    typer.echo(str(destination))
