"""Ctrl+P actions for `cocli calling`.

Read and sync commands run the same application functions as the CLI.
Commands that place a real call or SMS ask for confirmation first.
Commands that need arguments the palette cannot collect open the CLI form
instead of writing config or dialing a number.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Optional

from ..application.call_recording_service import (
    SyncRecordingsResult,
    sync_twilio_recordings,
)
from ..application.sms_service import SyncSmsResult, sync_twilio_sms
from ..core.config import get_campaign, load_campaign_config, load_global_config
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

Severity = Literal["information", "warning", "error"]
Present = Literal["notify", "viewer", "usage"]


@dataclass(frozen=True)
class CallingCommandResult:
    text: str
    severity: Severity = "information"


@dataclass(frozen=True)
class CallingPaletteEntry:
    name: str
    help: str
    action_id: str
    present: Present
    confirm: Optional[str] = None
    usage: Optional[str] = None


def calling_palette_entries() -> list[CallingPaletteEntry]:
    """Palette rows, in CLI order. Names stay searchable as `calling <command>`."""
    return [
        CallingPaletteEntry(
            "calling set-provider",
            "Set the calling provider. Needs a provider name, so this shows the CLI form.",
            "set-provider",
            "usage",
            usage=(
                "cocli calling set-provider <google_voice|twilio|quo|openphone|browser_tab>\n\n"
                "Writes the provider into the local cocli config. "
                "The palette does not collect that argument."
            ),
        ),
        CallingPaletteEntry(
            "calling set-app-id",
            "Save the Edge PWA app id. Needs the id, so this shows the CLI form.",
            "set-app-id",
            "usage",
            usage=(
                "cocli calling set-app-id <edge-app-id>\n\n"
                "The id is per machine and stays in local cocli config."
            ),
        ),
        CallingPaletteEntry(
            "calling set-twilio",
            "Save Twilio credentials. Needs secrets and numbers, so this shows the CLI form.",
            "set-twilio",
            "usage",
            usage=(
                "cocli calling set-twilio --account-sid AC... --caller-id +1... --my-phone +1...\n\n"
                "Also accepts --auth-token or --api-key/--api-secret, plus "
                "--recording-callback and --low-balance-threshold. "
                "The palette does not collect credentials."
            ),
        ),
        CallingPaletteEntry(
            "calling balance",
            "Check the Twilio balance. Same as `cocli calling balance`.",
            "balance",
            "notify",
        ),
        CallingPaletteEntry(
            "calling sync-messages",
            "Poll Twilio SMS into company notes. Same as `cocli calling sync-messages`.",
            "sync-messages",
            "notify",
        ),
        CallingPaletteEntry(
            "calling sync-recordings",
            "Poll Twilio call recordings into company notes. Same as `cocli calling sync-recordings`.",
            "sync-recordings",
            "notify",
        ),
        CallingPaletteEntry(
            "calling inspect-recordings",
            "List recent Twilio calls and recordings. Same as `cocli calling inspect-recordings`.",
            "inspect-recordings",
            "viewer",
        ),
        CallingPaletteEntry(
            "calling status",
            "Show the resolved calling provider. Same as `cocli calling status`.",
            "status",
            "viewer",
        ),
        CallingPaletteEntry(
            "calling test",
            "Dial a number with the current provider. Needs the number, so this shows the CLI form.",
            "test",
            "usage",
            usage=(
                "cocli calling test <phone>\n\n"
                "Places a real call. The palette does not collect the destination."
            ),
        ),
        CallingPaletteEntry(
            "calling test-voice",
            "Place a one-leg test call to your bridge phone. Asks before dialing.",
            "test-voice",
            "notify",
            confirm=(
                "Place a Twilio test call to your bridge phone (my_phone)? "
                "This dials a real number."
            ),
        ),
        CallingPaletteEntry(
            "calling test-sms",
            "Send a test SMS to your bridge phone. Asks before sending.",
            "test-sms",
            "notify",
            confirm=(
                "Send a Twilio test SMS to your bridge phone (my_phone)? "
                "This sends a real message."
            ),
        ),
        CallingPaletteEntry(
            "calling phone-status",
            "Show Twilio number webhooks and capabilities. Same as `cocli calling phone-status`.",
            "phone-status",
            "viewer",
        ),
        CallingPaletteEntry(
            "calling set-sms-forwarding",
            "Set the inbound SMS webhook. Needs a URL, so this shows the CLI form.",
            "set-sms-forwarding",
            "usage",
            usage=(
                "cocli calling set-sms-forwarding --twiml-url https://...\n\n"
                "Optional --phone defaults to the configured caller id. "
                "The palette does not collect the webhook URL."
            ),
        ),
    ]


def execute_calling_command(action_id: str) -> CallingCommandResult:
    """Run one palette action. Looked up at call time so tests can patch runners."""
    runners: dict[str, Callable[[], CallingCommandResult]] = {
        "balance": run_balance,
        "sync-messages": run_sync_messages,
        "sync-recordings": run_sync_recordings,
        "inspect-recordings": run_inspect_recordings,
        "status": run_status,
        "test-voice": run_test_voice,
        "test-sms": run_test_sms,
        "phone-status": run_phone_status,
    }
    runner = runners.get(action_id)
    if runner is None:
        return CallingCommandResult(
            f"{action_id} is not run from the palette.",
            severity="warning",
        )
    return runner()


def summarize_sms_sync(result: SyncSmsResult) -> CallingCommandResult:
    if result.errors:
        return CallingCommandResult("\n".join(result.errors), severity="error")
    if result.synced_count:
        return CallingCommandResult(
            f"Synced {result.synced_count} SMS messages "
            f"({result.matched_count} matched, {result.unmatched_count} in inbox)."
        )
    if result.skipped_count:
        return CallingCommandResult(
            f"No new messages ({result.skipped_count} already recorded)."
        )
    return CallingCommandResult("No incoming SMS messages found on Twilio.")


def summarize_recording_sync(result: SyncRecordingsResult) -> CallingCommandResult:
    lines: list[str] = []
    if result.errors:
        lines.extend(result.errors)
    if result.synced_count:
        lines.append(
            f"Synced {result.synced_count} recording(s) "
            f"({result.matched_count} matched)."
        )
    elif not result.errors:
        lines.append("No new recordings.")
    if result.unmatched_count:
        lines.append(
            f"{result.unmatched_count} recording(s) skipped: no company matched."
        )
    if result.skipped_count:
        lines.append(f"{result.skipped_count} recording(s) already synced.")
    severity: Severity = "error" if result.errors and not result.synced_count else "information"
    if result.errors and result.synced_count:
        severity = "warning"
    return CallingCommandResult("\n".join(lines), severity=severity)


def run_sync_messages() -> CallingCommandResult:
    result = sync_twilio_sms(campaign_name=get_campaign(), limit=50)
    return summarize_sms_sync(result)


def run_sync_recordings() -> CallingCommandResult:
    result = sync_twilio_recordings(campaign_name=get_campaign(), limit=50)
    return summarize_recording_sync(result)


def run_balance() -> CallingCommandResult:
    campaign = get_campaign()
    provider = get_calling_provider(campaign)
    if not isinstance(provider, TwilioBridgeCallingProvider):
        return CallingCommandResult(
            "Balance is only available when the calling provider is twilio.",
            severity="warning",
        )
    if not provider.is_configured():
        return CallingCommandResult(
            "Twilio is not fully configured. Run `cocli calling set-twilio` first.",
            severity="error",
        )
    is_low, bal, curr = provider.is_low_balance(bypass_cache=True)
    if bal is None:
        return CallingCommandResult(
            "Could not fetch the Twilio balance.",
            severity="error",
        )
    currency = curr or "USD"
    if is_low:
        return CallingCommandResult(
            f"Twilio balance is low: ${bal:.2f} {currency} "
            f"(threshold ${provider.low_balance_threshold:.2f}).",
            severity="warning",
        )
    return CallingCommandResult(
        f"Twilio balance: ${bal:.2f} {currency} "
        f"(threshold ${provider.low_balance_threshold:.2f})."
    )


def run_phone_status() -> CallingCommandResult:
    campaign = get_campaign()
    provider = get_calling_provider(campaign)
    if not isinstance(provider, TwilioBridgeCallingProvider):
        return CallingCommandResult(
            "Phone status is only available when the calling provider is twilio.",
            severity="warning",
        )
    if not provider.is_configured():
        return CallingCommandResult(
            "Twilio is not fully configured. Run `cocli calling set-twilio` first.",
            severity="error",
        )
    info = provider.get_incoming_phone_number(provider.caller_id)
    if not info:
        err = provider.last_error or "Unknown error"
        return CallingCommandResult(
            f"Could not find {provider.caller_id}: {err}",
            severity="error",
        )
    caps = info.get("capabilities") or {}
    cap_names = [str(key).upper() for key, enabled in caps.items() if enabled]
    sms_url = info.get("sms_url") or "(none)"
    voice_url = info.get("voice_url") or "(none)"
    text = "\n".join(
        [
            f"Phone: {info.get('phone_number')}",
            f"SID: {info.get('sid')}",
            f"Name: {info.get('friendly_name') or '(none)'}",
            f"Capabilities: {', '.join(cap_names) if cap_names else '(none)'}",
            f"SMS webhook: {sms_url} ({info.get('sms_method') or 'POST'})",
            f"Voice webhook: {voice_url}",
        ]
    )
    return CallingCommandResult(text)


def run_inspect_recordings() -> CallingCommandResult:
    campaign = get_campaign()
    provider = get_calling_provider(campaign)
    if not isinstance(provider, TwilioBridgeCallingProvider):
        return CallingCommandResult(
            "inspect-recordings is only available when the calling provider is twilio.",
            severity="warning",
        )
    if not provider.is_configured():
        return CallingCommandResult(
            "Twilio is not fully configured. Run `cocli calling set-twilio` first.",
            severity="error",
        )
    calls = provider.fetch_calls(limit=15)
    if not calls and provider.last_error:
        return CallingCommandResult(provider.last_error, severity="error")
    if not calls:
        return CallingCommandResult("No calls found on this Twilio account.")
    lines = [f"Found {len(calls)} recent call(s):"]
    for call in calls:
        sid = call.get("sid")
        parent = call.get("parent_call_sid")
        leg = "child" if parent else "parent"
        lines.append(
            f"{sid} {leg} to={call.get('to')} from={call.get('from')} "
            f"status={call.get('status')} duration={call.get('duration')}s"
            + (f" parent={parent}" if parent else "")
        )
        recordings = provider.fetch_recordings(call_sid=sid) if sid else []
        if not recordings:
            lines.append("  no recordings")
            continue
        for recording in recordings:
            rsid = recording.get("sid")
            lines.append(
                f"  recording {rsid} duration={recording.get('duration')}s "
                f"source={recording.get('source')}"
            )
            transcriptions = (
                provider.fetch_transcriptions(recording_sid=rsid) if rsid else []
            )
            if transcriptions:
                for item in transcriptions:
                    lines.append(
                        f"    transcription {item.get('sid')} status={item.get('status')}"
                    )
            else:
                lines.append("    no transcription")
    if provider.last_error:
        lines.append(f"Note: {provider.last_error}")
    return CallingCommandResult("\n".join(lines))


def run_test_voice() -> CallingCommandResult:
    campaign = get_campaign()
    provider = get_calling_provider(campaign)
    if not isinstance(provider, TwilioBridgeCallingProvider):
        return CallingCommandResult(
            "test-voice is only supported for the twilio provider.",
            severity="warning",
        )
    target = provider.my_phone
    if not target:
        return CallingCommandResult(
            "No bridge phone configured.",
            severity="error",
        )
    ok, res = provider.test_voice_call(target)
    if ok:
        return CallingCommandResult(f"Test call placed to {target} (SID {res}).")
    return CallingCommandResult(f"Test call failed: {res}", severity="error")


def run_test_sms() -> CallingCommandResult:
    campaign = get_campaign()
    provider = get_calling_provider(campaign)
    if not isinstance(provider, TwilioBridgeCallingProvider):
        return CallingCommandResult(
            "test-sms is only supported for the twilio provider.",
            severity="warning",
        )
    target = provider.my_phone
    if not target:
        return CallingCommandResult(
            "No bridge phone configured.",
            severity="error",
        )
    ok, res = provider.send_sms(
        to_phone=target,
        body="CoCli Test: Twilio SMS is working properly!",
    )
    if ok:
        return CallingCommandResult(f"Test SMS sent to {target} (SID {res}).")
    return CallingCommandResult(f"Test SMS failed: {res}", severity="error")


def run_status() -> CallingCommandResult:
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
    lines = [
        f"Campaign: {campaign or '(none)'}",
        f"Configured provider: {provider_name}",
    ]
    if str(provider_name).lower() in ("twilio", "twilio_bridge", "bridge"):
        lines.extend(_twilio_status_lines(campaign))
    else:
        lines.extend(_google_voice_status_lines(campaign))
    lines.append(f"Resolved provider class: {type(provider).__name__}")
    return CallingCommandResult("\n".join(lines))


def _twilio_status_lines(campaign: Optional[str]) -> list[str]:
    tw_cfg = twilio_config(campaign)
    provider = TwilioBridgeCallingProvider(
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
    sid_raw = provider.account_sid or ""
    sid_masked = (
        f"{sid_raw[:6]}...{sid_raw[-4:]}" if len(sid_raw) > 10 else (sid_raw or "(not set)")
    )
    if provider.api_key:
        auth_status = f"API Key ({provider.api_key[:6]}...)"
    elif provider.auth_token:
        auth_status = "Auth Token (set)"
    else:
        auth_status = "(not set)"
    lines = [
        f"Twilio Account SID: {sid_masked}",
        f"Twilio Auth: {auth_status}",
        f"Caller ID: {provider.caller_id or '(not set)'}",
        f"Bridge phone: {provider.my_phone or '(not set)'}",
        f"Recording callback: {provider.recording_callback_url or '(not set)'}",
        f"Low balance threshold: ${provider.low_balance_threshold:.2f}",
        f"Twilio status: {'Ready' if provider.is_configured() else 'Incomplete'}",
    ]
    if not provider.is_configured():
        return lines
    account = provider.get_account_info()
    if account:
        lines.append(f"Account type: {account.get('type', 'Full')}")
        lines.append(f"Account status: {account.get('status', 'active')}")
    number = provider.get_incoming_phone_number()
    if number:
        lines.append(f"SMS webhook: {number.get('sms_url') or '(none)'}")
        lines.append(f"Voice webhook: {number.get('voice_url') or '(none)'}")
    is_low, bal, curr = provider.is_low_balance()
    if bal is None:
        lines.append("Balance: (could not retrieve)")
    else:
        state = "LOW" if is_low else "OK"
        lines.append(f"Balance: ${bal:.2f} {curr or 'USD'} ({state})")
    return lines


def _google_voice_status_lines(campaign: Optional[str]) -> list[str]:
    gv_cfg = google_voice_config(campaign)
    lines: list[str] = []
    configured_id = gv_cfg.get("edge_app_id")
    if configured_id:
        installed = "installed" if is_pwa_installed(configured_id) else "not installed"
        lines.append(f"edge_app_id: {configured_id} ({installed})")
    else:
        lines.append("edge_app_id: (not set)")
    discovered = discover_installed_voice_pwa()
    if discovered:
        lines.append(
            f"Auto-discovered PWA: {discovered.get('app_id')} ({discovered.get('browser')})"
        )
    else:
        lines.append("Auto-discovered PWA: (none)")
    lines.append(f"msedge_proxy.exe: {find_msedge_proxy() or '(not found)'}")
    lines.append(f"Chromium app binary: {find_browser_app_binary() or '(not found)'}")
    return lines
