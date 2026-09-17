"""Configure and test the pluggable calling provider (see
cocli/utils/calling_provider.py for the abstraction and why edge_app_id
lives here instead of in campaign config.toml)."""

from __future__ import annotations


import typer
from rich.console import Console

from ..core.config import get_campaign, load_global_config, save_config
from ..utils.calling_provider import find_msedge_proxy, google_voice_config, get_calling_provider

app = typer.Typer(no_args_is_help=True, help="Configure the phone-dialer provider.")
console = Console()


@app.command("set-app-id")
def set_app_id(app_id: str) -> None:
    """Save the Edge PWA app-id for the Google Voice provider.

    This id is per-machine (Edge assigns a random 32-char hex id per
    installed PWA on install) - it's stored in the local, non-synced
    cocli_config.toml, never in a campaign's config.toml. If the PWA
    gets reinstalled or you switch machines, re-run this with the new id.
    """
    config = load_global_config()
    gv_cfg = dict(config.get("google_voice", {}) or {})
    gv_cfg["edge_app_id"] = app_id
    gv_cfg.setdefault("provider", "google_voice")
    config["google_voice"] = gv_cfg
    save_config(config)
    console.print(f"[bold green]Saved edge_app_id={app_id} to global config.[/bold green]")


@app.command("status")
def status() -> None:
    """Show the resolved calling provider config and whether the Edge PWA
    launcher (msedge_proxy.exe) can actually be found on this machine."""
    campaign = get_campaign()
    gv_cfg = google_voice_config(campaign)
    provider = get_calling_provider(campaign)

    console.print(f"Campaign: {campaign or '(none)'}")
    console.print(f"Configured provider: {gv_cfg.get('provider', 'google_voice')}")
    console.print(f"edge_app_id: {gv_cfg.get('edge_app_id') or '(not set)'}")
    console.print(f"msedge_proxy.exe found: {find_msedge_proxy() or '(not found)'}")
    console.print(f"Resolved provider class: {type(provider).__name__}")


@app.command("test")
def test(phone: str) -> None:
    """Actually dial `phone` with the currently configured provider - use
    this after set-app-id to confirm the PWA window opens correctly."""
    campaign = get_campaign()
    provider = get_calling_provider(campaign)
    ok = provider.dial(phone, campaign)
    if ok:
        console.print(f"[bold green]Launched call to {phone} via {type(provider).__name__}.[/bold green]")
    else:
        console.print(f"[bold red]Could not launch a call to {phone}.[/bold red]")
        raise typer.Exit(code=1)
