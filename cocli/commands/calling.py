"""Configure and test the pluggable calling provider (see
cocli/utils/calling_provider.py for the abstraction and why edge_app_id
lives here instead of in campaign config.toml)."""

from __future__ import annotations


import typer
from rich.console import Console

from ..core.config import (
    get_campaign,
    load_campaign_config,
    load_global_config,
    save_config,
)
from ..utils.calling_provider import (
    TwilioBridgeCallingProvider,
    discover_installed_voice_pwa,
    find_browser_app_binary,
    find_msedge_proxy,
    get_calling_provider,
    google_voice_config,
    is_pwa_installed,
    twilio_config,
)

app = typer.Typer(no_args_is_help=True, help="Configure the phone-dialer provider.")
console = Console()


@app.command("set-provider")
def set_provider(provider: str) -> None:
    """Set the calling provider ('google_voice', 'twilio', 'quo', 'openphone', or 'browser_tab')."""
    config = load_global_config()
    calling_cfg = dict(config.get("calling", {}) or {})
    calling_cfg["provider"] = provider
    config["calling"] = calling_cfg

    gv_cfg = dict(config.get("google_voice", {}) or {})
    gv_cfg["provider"] = provider
    config["google_voice"] = gv_cfg

    save_config(config)
    console.print(
        f"[bold green]Saved provider={provider} to global config.[/bold green]"
    )


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
    console.print(
        f"[bold green]Saved edge_app_id={app_id} to global config.[/bold green]"
    )


@app.command("set-twilio")
def set_twilio(
    account_sid: str = typer.Option(
        ..., "--account-sid", help="Twilio Account SID (e.g. AC...)"
    ),
    auth_token: str = typer.Option(..., "--auth-token", help="Twilio Auth Token"),
    caller_id: str = typer.Option(
        ..., "--caller-id", help="Twilio outbound business caller ID"
    ),
    my_phone: str = typer.Option(
        ..., "--my-phone", help="Your mobile phone number to ring first"
    ),
    recording_callback: str = typer.Option(
        "", "--recording-callback", help="Optional webhook URL for recordings"
    ),
    low_balance_threshold: float = typer.Option(
        20.0, "--low-balance-threshold", help="Warning threshold in USD for low balance"
    ),
) -> None:
    """Save Twilio credentials and phone numbers for call bridging."""
    config = load_global_config()
    tw_cfg = dict(config.get("twilio", {}) or {})
    if account_sid:
        tw_cfg["account_sid"] = account_sid
    if auth_token:
        tw_cfg["auth_token"] = auth_token
    if caller_id:
        tw_cfg["caller_id"] = caller_id
    if my_phone:
        tw_cfg["my_phone"] = my_phone
    if recording_callback:
        tw_cfg["recording_callback_url"] = recording_callback
    if low_balance_threshold is not None:
        tw_cfg["low_balance_threshold"] = low_balance_threshold
    config["twilio"] = tw_cfg
    save_config(config)
    console.print(
        "[bold green]Saved Twilio configuration to global config.[/bold green]"
    )


@app.command("balance")
def balance(
    refresh: bool = typer.Option(
        False, "--refresh", "-r", help="Bypass cached balance and fetch live"
    ),
) -> None:
    """Check the Twilio account balance and report whether it is low."""
    campaign = get_campaign()
    provider = get_calling_provider(campaign)
    if not isinstance(provider, TwilioBridgeCallingProvider):
        console.print(
            "[yellow]Balance checking is only active when calling provider is set to 'twilio'.[/yellow]"
        )
        return

    if not provider.is_configured():
        console.print(
            "[bold red]Twilio is not fully configured. Run 'cocli calling set-twilio' first.[/bold red]"
        )
        return

    is_low, bal, curr = provider.is_low_balance(bypass_cache=refresh)
    if bal is not None:
        c = curr or "USD"
        if is_low:
            console.print(
                f"[bold yellow]⚠️ Twilio Balance is LOW: ${bal:.2f} {c} "
                f"(Threshold: ${provider.low_balance_threshold:.2f})[/bold yellow]"
            )
        else:
            console.print(
                f"[bold green]Twilio Balance: ${bal:.2f} {c} "
                f"(Threshold: ${provider.low_balance_threshold:.2f})[/bold green]"
            )
    else:
        console.print(
            "[bold red]Could not fetch Twilio balance. Check network or credentials.[/bold red]"
        )


@app.command("sync-messages")
def sync_messages(
    limit: int = typer.Option(
        50, "--limit", "-l", help="Max messages to fetch from Twilio"
    ),
) -> None:
    """Poll Twilio for incoming SMS replies and sync them into company Activity timelines."""
    from ..application.sms_service import sync_twilio_sms

    campaign = get_campaign()
    console.print("[dim]Checking Twilio for new incoming SMS messages...[/dim]")
    result = sync_twilio_sms(campaign_name=campaign, limit=limit)

    if result.errors:
        for err in result.errors:
            console.print(f"[bold red]{err}[/bold red]")

    if result.synced_count > 0:
        console.print(
            f"[bold green]Synced {result.synced_count} SMS messages "
            f"({result.matched_count} matched to companies, {result.unmatched_count} in inbox).[/bold green]"
        )
        for note_path in result.notes_created:
            console.print(f"  💬 [cyan]{note_path.name}[/cyan]")
    elif not result.errors:
        if result.skipped_count > 0:
            console.print(
                f"[dim]No new messages to sync ({result.skipped_count} already recorded).[/dim]"
            )
        else:
            console.print("[dim]No incoming SMS messages found on Twilio.[/dim]")


@app.command("status")
def status() -> None:
    """Show the resolved calling provider config and whether the Edge PWA
    launcher (msedge_proxy.exe) or Chromium app launcher can actually be found."""
    campaign = get_campaign()
    camp_cfg = load_campaign_config(campaign) if campaign else {}
    global_cfg = load_global_config()
    provider_name = (
        camp_cfg.get("calling", {}).get("provider")
        or camp_cfg.get("google_voice", {}).get("provider")
        or global_cfg.get("calling", {}).get("provider")
        or global_cfg.get("google_voice", {}).get("provider")
        or global_cfg.get("twilio", {}).get("provider")
        or "google_voice"
    )
    provider = get_calling_provider(campaign)

    console.print(f"Campaign: {campaign or '(none)'}")
    console.print(f"Configured provider: {provider_name}")

    if str(provider_name).lower() in ("twilio", "twilio_bridge", "bridge"):
        tw_cfg = twilio_config(campaign)
        tw_provider = TwilioBridgeCallingProvider(
            account_sid=tw_cfg.get("account_sid"),
            auth_token=tw_cfg.get("auth_token"),
            caller_id=tw_cfg.get("caller_id") or tw_cfg.get("business_number"),
            my_phone=tw_cfg.get("my_phone") or tw_cfg.get("bridge_to"),
            recording_callback_url=tw_cfg.get("recording_callback_url"),
            record=bool(tw_cfg.get("record", True)),
            low_balance_threshold=float(tw_cfg.get("low_balance_threshold", 20.0)),
        )
        sid_raw = tw_provider.account_sid or ""
        sid_masked = (
            f"{sid_raw[:6]}...{sid_raw[-4:]}"
            if len(sid_raw) > 10
            else (sid_raw or "(not set)")
        )
        token_status = "(set)" if tw_provider.auth_token else "(not set)"
        ready_status = (
            "[bold green]Ready[/bold green]"
            if tw_provider.is_configured()
            else "[bold red]Incomplete[/bold red]"
        )
        console.print(f"Twilio Account SID: {sid_masked}")
        console.print(f"Twilio Auth Token: {token_status}")
        console.print(
            f"Twilio Caller ID (Business): {tw_provider.caller_id or '(not set)'}"
        )
        console.print(
            f"Twilio My Phone (Bridge To): {tw_provider.my_phone or '(not set)'}"
        )
        console.print(
            f"Twilio Recording Callback: {tw_provider.recording_callback_url or '(not set)'}"
        )
        console.print(
            f"Twilio Low Balance Threshold: ${tw_provider.low_balance_threshold:.2f}"
        )
        console.print(f"Twilio Status: {ready_status}")
        if tw_provider.is_configured():
            is_low, bal, curr = tw_provider.is_low_balance()
            if bal is not None:
                c = curr or "USD"
                if is_low:
                    console.print(
                        f"Twilio Balance: [bold yellow]${bal:.2f} {c} "
                        f"(⚠️ Low balance: below ${tw_provider.low_balance_threshold:.2f})[/bold yellow]"
                    )
                else:
                    console.print(
                        f"Twilio Balance: [bold green]${bal:.2f} {c} (OK)[/bold green]"
                    )
            else:
                console.print("Twilio Balance: (could not retrieve balance)")
    else:
        gv_cfg = google_voice_config(campaign)
        configured_id = gv_cfg.get("edge_app_id")
        if configured_id:
            installed = is_pwa_installed(configured_id)
            status_suffix = (
                " [bold green](installed)[/bold green]"
                if installed
                else " [yellow](not installed on this machine)[/yellow]"
            )
            console.print(f"edge_app_id: {configured_id}{status_suffix}")
        else:
            console.print("edge_app_id: (not set)")

        discovered = discover_installed_voice_pwa()
        if discovered:
            console.print(
                f"Auto-discovered PWA: app-id={discovered.get('app_id')} "
                f"({discovered.get('browser')}, path={discovered.get('path')})"
            )
        else:
            console.print(
                "Auto-discovered PWA: (none found, will use native Chromium --app mode)"
            )

        console.print(f"msedge_proxy.exe found: {find_msedge_proxy() or '(not found)'}")
        console.print(
            f"Chromium app binary found: {find_browser_app_binary() or '(not found)'}"
        )

    console.print(f"Resolved provider class: {type(provider).__name__}")


@app.command("test")
def test(phone: str) -> None:
    """Actually dial `phone` with the currently configured provider - use
    this after set-app-id to confirm the PWA window opens correctly."""
    campaign = get_campaign()
    provider = get_calling_provider(campaign)
    if isinstance(provider, TwilioBridgeCallingProvider):
        is_low, bal, curr = provider.is_low_balance()
        if is_low and bal is not None:
            console.print(
                f"[bold yellow]⚠️ Warning: Twilio balance is low: ${bal:.2f} {curr or 'USD'} "
                f"(Threshold: ${provider.low_balance_threshold:.2f})[/bold yellow]"
            )
    ok = provider.dial(phone, campaign)
    if ok:
        console.print(
            f"[bold green]Launched call to {phone} via {type(provider).__name__}.[/bold green]"
        )
    else:
        console.print(f"[bold red]Could not launch a call to {phone}.[/bold red]")
        raise typer.Exit(code=1)
