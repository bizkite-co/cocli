"""Configure and test the pluggable calling provider (see
cocli/utils/calling_provider.py for the abstraction and why edge_app_id
lives here instead of in campaign config.toml)."""

from __future__ import annotations

from typing import Optional

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
    auth_token: str = typer.Option("", "--auth-token", help="Twilio Auth Token"),
    api_key: str = typer.Option(
        "", "--api-key", help="Twilio API Key SID (e.g. SK...)"
    ),
    api_secret: str = typer.Option(
        "", "--api-secret", help="Twilio API Key Secret"
    ),
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
        5.0, "--low-balance-threshold", help="Warning threshold in USD for low balance"
    ),
) -> None:
    """Save Twilio credentials and phone numbers for call bridging."""
    config = load_global_config()
    tw_cfg = dict(config.get("twilio", {}) or {})
    if account_sid:
        tw_cfg["account_sid"] = account_sid
    if auth_token:
        tw_cfg["auth_token"] = auth_token
    if api_key:
        tw_cfg["api_key"] = api_key
    if api_secret:
        tw_cfg["api_secret"] = api_secret
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
            api_key=tw_cfg.get("api_key"),
            api_secret=tw_cfg.get("api_secret"),
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
        if tw_provider.api_key:
            auth_status = f"API Key ({tw_provider.api_key[:6]}...)"
        elif tw_provider.auth_token:
            auth_status = "Auth Token (set)"
        else:
            auth_status = "(not set)"

        ready_status = (
            "[bold green]Ready[/bold green]"
            if tw_provider.is_configured()
            else "[bold red]Incomplete[/bold red]"
        )
        console.print(f"Twilio Account SID: {sid_masked}")
        console.print(f"Twilio Auth: {auth_status}")
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
            # Query live account details
            acc_info = tw_provider.get_account_info()
            if acc_info:
                acc_type = acc_info.get("type", "Full")
                type_styled = (
                    "[bold green]Full (Upgraded)[/bold green]"
                    if str(acc_type).lower() == "full"
                    else f"[bold yellow]{acc_type}[/bold yellow]"
                )
                console.print(f"Twilio Account Type: {type_styled}")
                console.print(f"Twilio Account Status: [green]{acc_info.get('status', 'active')}[/green]")
            num_info = tw_provider.get_incoming_phone_number()
            if num_info:
                sms_url = num_info.get("sms_url")
                if sms_url:
                    console.print(f"Twilio SMS Forwarding (SmsUrl): [bold green]{sms_url}[/bold green]")
                else:
                    console.print("Twilio SMS Forwarding (SmsUrl): [dim](none configured - SMS forwarding inactive)[/dim]")

            trust_info = tw_provider.get_trusthub_status()
            if trust_info:
                prof_name = trust_info.get("friendly_name", "Primary Profile")
                prof_status = trust_info.get("status", "unknown")
                policy_desc = trust_info.get("policy_name") or "Profile"
                if "individual" in policy_desc.lower():
                    policy_label = "Individual"
                elif "business" in policy_desc.lower():
                    policy_label = "Business"
                else:
                    policy_label = policy_desc

                status_styled = (
                    f"[bold green]{prof_status}[/bold green]"
                    if "approved" in prof_status.lower()
                    else f"[bold yellow]{prof_status}[/bold yellow]"
                )
                console.print(
                    f"Twilio TrustHub Profile: {prof_name} ({policy_label}) - {status_styled}"
                )

            dial_perm = tw_provider.get_dialing_permissions("US")
            if dial_perm:
                low_risk = (
                    "[bold green]Enabled[/bold green]"
                    if dial_perm.get("low_risk_numbers_enabled")
                    else "[bold red]Disabled[/bold red]"
                )
                high_risk = (
                    "[bold green]Enabled[/bold green]"
                    if dial_perm.get("high_risk_special_numbers_enabled")
                    else "[dim]Disabled[/dim]"
                )
                console.print(
                    f"Twilio US Dialing Permissions: Low Risk: {low_risk}, High Risk: {high_risk}"
                )

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
        err = getattr(provider, "last_error", None)
        console.print(f"[bold red]Could not launch a call to {phone}.[/bold red]")
        if err:
            console.print(f"[yellow]{err}[/yellow]")
            if "21216" in err:
                console.print(
                    "\n[bold yellow]Note on Error 21216:[/] Twilio blocked this outbound call. "
                    "Since your Customer Profile is approved, this is typically Twilio's automated "
                    "fraud protection filter on newly funded accounts. "
                    "Submit a ticket at https://help.twilio.com to request lifting the outbound voice block."
                )
        raise typer.Exit(code=1)


@app.command("test-voice")
def test_voice(
    phone: Optional[str] = typer.Argument(
        None, help="Optional phone number to call (defaults to configured my_phone)"
    ),
) -> None:
    """Place a direct single-leg test call with an automated spoken confirmation.

    Unlike 'test', this does not bridge calls together, avoiding feedback loops.
    """
    campaign = get_campaign()
    provider = get_calling_provider(campaign)
    if not isinstance(provider, TwilioBridgeCallingProvider):
        console.print(
            "[yellow]test-voice is only supported for the 'twilio' calling provider.[/yellow]"
        )
        raise typer.Exit(code=1)

    target = phone or provider.my_phone
    if not target:
        console.print(
            "[bold red]No phone number provided and no 'my_phone' configured in Twilio settings.[/bold red]"
        )
        raise typer.Exit(code=1)

    console.print(f"Initiating test voice call to [cyan]{target}[/cyan]...")
    ok, res = provider.test_voice_call(target)
    if ok:
        console.print(
            f"[bold green]✓ Test voice call placed successfully! (Call SID: {res})[/bold green]"
        )
        console.print("Answer your phone to hear the automated confirmation message.")
    else:
        console.print(f"[bold red]✗ Test voice call failed:[/] [yellow]{res}[/yellow]")
        if res and "21216" in res:
            console.print(
                "\n[bold yellow]Note on Error 21216:[/] Twilio blocked this call. "
                "Contact Twilio Support (https://help.twilio.com) to lift the automated outbound voice restriction."
            )
        raise typer.Exit(code=1)


@app.command("test-sms")
def test_sms(
    phone: Optional[str] = typer.Argument(
        None, help="Optional phone number to text (defaults to configured my_phone)"
    ),
    message: str = typer.Option(
        "CoCli Test: Twilio SMS is working properly!",
        "--message",
        "-m",
        help="Text message body to send",
    ),
) -> None:
    """Send a test SMS message from your Twilio number to your phone."""
    campaign = get_campaign()
    provider = get_calling_provider(campaign)
    if not isinstance(provider, TwilioBridgeCallingProvider):
        console.print(
            "[yellow]test-sms is only supported for the 'twilio' calling provider.[/yellow]"
        )
        raise typer.Exit(code=1)

    target = phone or provider.my_phone
    if not target:
        console.print(
            "[bold red]No phone number provided and no 'my_phone' configured in Twilio settings.[/bold red]"
        )
        raise typer.Exit(code=1)

    console.print(f"Sending test SMS to [cyan]{target}[/cyan]...")
    ok, res = provider.send_sms(to_phone=target, body=message)
    if ok:
        console.print(
            f"[bold green]✓ Test SMS sent successfully! (Message SID: {res})[/bold green]"
        )
    else:
        console.print(f"[bold red]✗ Test SMS failed:[/] [yellow]{res}[/yellow]")
        raise typer.Exit(code=1)


@app.command("phone-status")
def phone_status(
    phone: Optional[str] = typer.Option(
        None,
        "--phone",
        "-p",
        help="Phone number to query (defaults to configured caller_id)",
    ),
) -> None:
    """Inspect Twilio incoming phone number configuration, capabilities, and active webhooks."""
    campaign = get_campaign()
    provider = get_calling_provider(campaign)
    if not isinstance(provider, TwilioBridgeCallingProvider):
        console.print(
            "[yellow]Phone status inspection is only active when calling provider is 'twilio'.[/yellow]"
        )
        return
    if not provider.is_configured():
        console.print(
            "[bold red]Twilio is not fully configured. Run 'cocli calling set-twilio' first.[/bold red]"
        )
        return

    target = phone or provider.caller_id
    if not target:
        console.print(
            "[bold red]No phone number specified and no caller_id configured.[/bold red]"
        )
        return

    console.print(f"[dim]Querying Twilio API for phone number {target}...[/dim]")
    info = provider.get_incoming_phone_number(target)
    if not info:
        err = provider.last_error or "Unknown error"
        console.print(
            f"[bold red]Could not find phone number {target}: {err}[/bold red]"
        )
        return

    console.print(f"[bold]Phone Number:[/] [cyan]{info.get('phone_number')}[/cyan]")
    console.print(f"  SID: {info.get('sid')}")
    console.print(f"  Friendly Name: {info.get('friendly_name') or '(none)'}")
    caps = info.get("capabilities", {})
    cap_strs = [k.upper() for k, v in caps.items() if v]
    console.print(f"  Capabilities: {', '.join(cap_strs) if cap_strs else '(none)'}")
    sms_url = info.get("sms_url")
    if sms_url:
        console.print(
            f"  SMS Webhook (SmsUrl): [bold green]{sms_url}[/bold green] ({info.get('sms_method', 'POST')})"
        )
    else:
        console.print(
            "  SMS Webhook (SmsUrl): [bold yellow](none configured - SMS forwarding inactive)[/bold yellow]"
        )
    voice_url = info.get("voice_url")
    if voice_url:
        console.print(f"  Voice Webhook: {voice_url}")


@app.command("set-sms-forwarding")
def set_sms_forwarding(
    twiml_url: str = typer.Option(
        ...,
        "--twiml-url",
        "-u",
        help="The TwiML Bin URL or webhook URL (e.g. https://handler.twilio.com/twiml/EH...)",
    ),
    phone: Optional[str] = typer.Option(
        None,
        "--phone",
        "-p",
        help="Twilio phone number to configure (defaults to configured caller_id)",
    ),
) -> None:
    """Set the inbound SMS webhook (SmsUrl) on your Twilio phone number to forward messages."""
    campaign = get_campaign()
    provider = get_calling_provider(campaign)
    if not isinstance(provider, TwilioBridgeCallingProvider):
        console.print(
            "[yellow]SMS forwarding configuration is only active when calling provider is 'twilio'.[/yellow]"
        )
        return
    if not provider.is_configured():
        console.print(
            "[bold red]Twilio is not fully configured. Run 'cocli calling set-twilio' first.[/bold red]"
        )
        return

    target = phone or provider.caller_id
    if not target:
        console.print(
            "[bold red]No phone number specified and no caller_id configured.[/bold red]"
        )
        return

    console.print(f"[dim]Setting SmsUrl on {target} to {twiml_url}...[/dim]")
    ok, result = provider.update_incoming_phone_number_sms_url(twiml_url, target)
    if ok:
        console.print(
            f"[bold green]Successfully updated Twilio phone number {target} (SID: {result})![/bold green]"
        )
        console.print(f"  Inbound SMS will now trigger: [cyan]{twiml_url}[/cyan]")
    else:
        console.print(f"[bold red]Failed to update Twilio SmsUrl: {result}[/bold red]")
        raise typer.Exit(code=1)
