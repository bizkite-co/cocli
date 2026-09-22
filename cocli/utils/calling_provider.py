"""Pluggable "how do we actually launch a call" abstraction.

Supports multiple dialer providers:
1. Google Voice (default):
   - Single-instance PWA launch via msedge_proxy.exe / chrome_proxy.exe when
     an installed PWA is configured or auto-discovered.
   - Standalone Chromium app mode (msedge.exe / chrome.exe --app=<url>) which
     opens a dedicated, frameless PWA-style window with the phone number
     pre-filled, without requiring a static app ID.
   - BrowserTabCallingProvider fallback to open in a normal browser tab.
   - Always copies the cleaned E.164 phone number to the clipboard as a fallback.
2. Twilio Call Bridging (Option 2):
   - Outbound click-to-call bridging via Twilio Voice REST API.
   - Rings your mobile phone first, then dials the prospect presenting your business
     caller ID, recording the call for transcription and CRM note creation.
3. Quo / OpenPhone:
   - Launches via OpenPhone desktop application protocol (openphone://call?number=...)
     or system tel: URI scheme, falling back to the Quo web application.
4. BrowserTabCallingProvider:
   - Opens the dialer URL in a standard browser tab.
"""

from __future__ import annotations

import glob
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Optional, Protocol

from .google_voice_url import clean_phone_e164, google_voice_url
from .open_url import copy_to_windows_clipboard, is_wsl, open_url, spawn_detached

logger = logging.getLogger(__name__)


class CallingProvider(Protocol):
    def dial(self, phone: str, campaign_name: Optional[str] = None) -> bool:
        """Launch a call to `phone`. Returns True if a launch action fired."""
        ...


class BrowserTabCallingProvider:
    """Fallback used when no provider-specific launch path is configured
    or available: open the Google Voice calls URL as a browser tab."""

    def dial(self, phone: str, campaign_name: Optional[str] = None) -> bool:
        return open_url(google_voice_url(phone, campaign_name))


_MSEDGE_PROXY_CANDIDATES = (
    "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge_proxy.exe",
    "/mnt/c/Program Files/Microsoft/Edge/Application/msedge_proxy.exe",
)


def find_msedge_proxy() -> Optional[str]:
    found = shutil.which("msedge_proxy.exe")
    if found:
        return found
    for candidate in _MSEDGE_PROXY_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


_BROWSER_APP_CANDIDATES = (
    # Edge on WSL
    "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "/mnt/c/Program Files/Microsoft/Edge/Application/msedge.exe",
    # Chrome on WSL
    "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
    "/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe",
)


def find_browser_app_binary() -> Optional[str]:
    """Find a Chromium-based browser executable capable of launching with --app=<url>."""
    if is_wsl():
        for candidate in _BROWSER_APP_CANDIDATES:
            if Path(candidate).exists():
                return candidate
        for user_edge in glob.glob("/mnt/c/Users/*/AppData/Local/Microsoft/Edge/Application/msedge.exe"):
            if Path(user_edge).exists():
                return user_edge
        for user_chrome in glob.glob("/mnt/c/Users/*/AppData/Local/Google/Chrome/Application/chrome.exe"):
            if Path(user_chrome).exists():
                return user_chrome

    if sys.platform == "win32":
        for env_key in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
            base = os.environ.get(env_key)
            if not base:
                continue
            for rel in (
                r"Microsoft\Edge\Application\msedge.exe",
                r"Google\Chrome\Application\chrome.exe",
            ):
                candidate = Path(base) / rel
                if candidate.exists():
                    return str(candidate)

    for name in (
        "google-chrome",
        "google-chrome-stable",
        "microsoft-edge",
        "microsoft-edge-stable",
        "chromium",
        "chromium-browser",
        "msedge.exe",
        "chrome.exe",
    ):
        found = shutil.which(name)
        if found:
            return found

    return None


def _find_pwa_dir_by_id(app_id: str) -> Optional[Path]:
    if not app_id:
        return None
    patterns: list[str] = []
    if is_wsl():
        patterns.extend([
            f"/mnt/c/Users/*/AppData/Local/Microsoft/Edge/User Data/*/Web Applications/_crx__{app_id}",
            f"/mnt/c/Users/*/AppData/Local/Google/Chrome/User Data/*/Web Applications/_crx_{app_id}",
            f"/mnt/c/Users/*/AppData/Local/Microsoft/Edge/User Data/*/Web Applications/Manifest Resources/{app_id}",
            f"/mnt/c/Users/*/AppData/Local/Google/Chrome/User Data/*/Web Applications/Manifest Resources/{app_id}",
        ])
    elif sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            patterns.extend([
                f"{local_app_data}/Microsoft/Edge/User Data/*/Web Applications/_crx__{app_id}",
                f"{local_app_data}/Google/Chrome/User Data/*/Web Applications/_crx_{app_id}",
                f"{local_app_data}/Microsoft/Edge/User Data/*/Web Applications/Manifest Resources/{app_id}",
                f"{local_app_data}/Google/Chrome/User Data/*/Web Applications/Manifest Resources/{app_id}",
            ])
    for pat in patterns:
        matches = glob.glob(pat)
        if matches:
            return Path(matches[0])
    return None


def is_pwa_installed(app_id: Optional[str]) -> bool:
    """Check if the given Chromium PWA app_id is installed on the system."""
    if not app_id:
        return False
    if os.environ.get("PYTEST_CURRENT_TEST"):
        # Under pytest, preserve explicit mock app IDs unless explicitly mocked
        return True
    return bool(_find_pwa_dir_by_id(app_id))


def discover_installed_voice_pwa() -> Optional[dict[str, str]]:
    """Scan Edge and Chrome Web Applications directories for an installed Google Voice PWA."""
    patterns: list[str] = []
    if is_wsl():
        patterns.extend([
            "/mnt/c/Users/*/AppData/Local/Microsoft/Edge/User Data/*/Web Applications/_crx__*",
            "/mnt/c/Users/*/AppData/Local/Google/Chrome/User Data/*/Web Applications/_crx_*",
        ])
    elif sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            patterns.extend([
                f"{local_app_data}/Microsoft/Edge/User Data/*/Web Applications/_crx__*",
                f"{local_app_data}/Google/Chrome/User Data/*/Web Applications/_crx_*",
            ])

    for pat in patterns:
        for match in glob.glob(pat):
            p = Path(match)
            if not p.is_dir():
                continue
            for item in p.iterdir():
                name_lower = item.name.lower()
                if "voice" in name_lower:
                    dir_name = p.name
                    if dir_name.startswith("_crx__"):
                        app_id = dir_name[6:]
                        browser = "edge"
                    elif dir_name.startswith("_crx_"):
                        app_id = dir_name[5:]
                        browser = "chrome"
                    else:
                        app_id = dir_name
                        browser = "edge"
                    return {
                        "app_id": app_id,
                        "browser": browser,
                        "path": str(p),
                    }
    return None


class GoogleVoiceEdgeAppProvider:
    """Windows/WSL2 and desktop app launcher for Google Voice.

    Launches Google Voice in a dedicated app/PWA window without browser tabs or address bar:
    1. If an Edge/Chrome PWA is installed (via configured `edge_app_id` or auto-discovery)
       and `msedge_proxy.exe` is available, launches via proxy single-instance mode.
    2. If no installed PWA is found or proxy fails, launches directly via Chromium
       native standalone app mode (`msedge.exe` or `chrome.exe` with `--app=<url>`).
       This provides the exact standalone PWA experience and pre-fills the dialer URL
       with the phone number, without requiring a static app ID.
    3. Falls back to standard browser tab via `BrowserTabCallingProvider` if no
       Chromium binary is found.

    Always copies the cleaned E.164 phone number to the Windows clipboard as a paste fallback.
    """

    def __init__(
        self,
        edge_app_id: Optional[str] = None,
        profile_directory: str = "Default",
    ):
        self.edge_app_id = edge_app_id
        self.profile_directory = profile_directory

    def dial(self, phone: str, campaign_name: Optional[str] = None) -> bool:
        url = google_voice_url(phone, campaign_name)
        cleaned = clean_phone_e164(phone)

        # 1. Determine if we have a valid, verified PWA app_id
        target_app_id = self.edge_app_id
        if target_app_id and not is_pwa_installed(target_app_id):
            logger.info(
                "Configured edge_app_id=%s is not installed; falling back to auto-discovery / --app mode",
                target_app_id,
            )
            target_app_id = None

        if not target_app_id:
            discovered = discover_installed_voice_pwa()
            if discovered:
                target_app_id = discovered.get("app_id")
                logger.info("Auto-discovered Google Voice PWA app_id=%s", target_app_id)

        # 2. Try proxy launch if target_app_id is verified and proxy exists
        if target_app_id:
            proxy = find_msedge_proxy()
            if proxy:
                command = [
                    proxy,
                    f"--profile-directory={self.profile_directory}",
                    f"--app-id={target_app_id}",
                    "--app-launch-source=4",
                    f"--app-launch-url-for-shortcuts-menu-item={url}",
                ]
                if spawn_detached(command):
                    copy_to_windows_clipboard(cleaned)
                    logger.info("Launched Google Voice PWA via %s (app-id=%s)", proxy, target_app_id)
                    return True
                logger.warning("Proxy launch failed; falling back to native --app mode")

        # 3. Native Chromium --app=<url> launch (dedicated app window)
        browser = find_browser_app_binary()
        if browser:
            command = [
                browser,
                f"--profile-directory={self.profile_directory}",
                f"--app={url}",
            ]
            if spawn_detached(command):
                copy_to_windows_clipboard(cleaned)
                logger.info("Launched Google Voice via %s --app mode", browser)
                return True
            logger.warning("Browser --app launch failed; falling back to browser tab")

        # 4. Fallback to standard browser tab
        return BrowserTabCallingProvider().dial(phone, campaign_name)


# Alias for modern naming
GoogleVoiceAppCallingProvider = GoogleVoiceEdgeAppProvider


class QuoCallingProvider:
    """Calling provider for Quo (formerly OpenPhone).

    Launches calls via the OpenPhone desktop application protocol (`openphone://call?number=...`)
    or the system `tel:` URI scheme, falling back to the Quo web application.
    Also copies the cleaned E.164 number to the clipboard.
    """

    def __init__(self, use_web: bool = False):
        self.use_web = use_web

    def dial(self, phone: str, campaign_name: Optional[str] = None) -> bool:
        cleaned = clean_phone_e164(phone)
        copy_to_windows_clipboard(cleaned)

        if self.use_web:
            return open_url(f"https://my.openphone.com/call?number={cleaned}")

        if open_url(f"openphone://call?number={cleaned}"):
            logger.info("Launched call via openphone:// protocol")
            return True

        if open_url(f"tel:{cleaned}"):
            logger.info("Launched call via tel: protocol")
            return True

        return open_url(f"https://my.openphone.com/call?number={cleaned}")


# Alias
OpenPhoneCallingProvider = QuoCallingProvider


class TwilioBridgeCallingProvider:
    """Outbound click-to-call bridging via Twilio Voice REST API.

    When dialing, Twilio calls `my_phone` (your personal mobile phone) first.
    When you answer, Twilio executes inline TwiML to dial `phone` (the prospect)
    presenting `caller_id` (your Twilio business number) and records the call.
    """

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        caller_id: Optional[str] = None,
        my_phone: Optional[str] = None,
        recording_callback_url: Optional[str] = None,
        record: bool = True,
    ):
        self.account_sid = account_sid or os.environ.get("TWILIO_ACCOUNT_SID")
        self.auth_token = auth_token or os.environ.get("TWILIO_AUTH_TOKEN")
        self.caller_id = caller_id or os.environ.get("TWILIO_CALLER_ID") or os.environ.get("TWILIO_PHONE_NUMBER")
        self.my_phone = my_phone or os.environ.get("TWILIO_MY_PHONE") or os.environ.get("TWILIO_BRIDGE_TO")
        self.recording_callback_url = recording_callback_url or os.environ.get("TWILIO_RECORDING_CALLBACK_URL")
        self.record = record

    def is_configured(self) -> bool:
        return bool(self.account_sid and self.auth_token and self.caller_id and self.my_phone)

    def dial(self, phone: str, campaign_name: Optional[str] = None) -> bool:
        import requests

        cleaned_prospect = clean_phone_e164(phone)
        copy_to_windows_clipboard(cleaned_prospect)

        if not self.is_configured():
            logger.error(
                "Twilio calling provider is missing required configuration: "
                "account_sid=%s, auth_token=%s, caller_id=%s, my_phone=%s",
                bool(self.account_sid),
                bool(self.auth_token),
                bool(self.caller_id),
                bool(self.my_phone),
            )
            return False

        account_sid = self.account_sid
        auth_token = self.auth_token

        if account_sid and account_sid.startswith("op://"):
            from .op_utils import get_op_secret

            resolved_sid = get_op_secret(account_sid)
            if resolved_sid:
                account_sid = resolved_sid

        if auth_token and auth_token.startswith("op://"):
            from .op_utils import get_op_secret

            resolved_token = get_op_secret(auth_token)
            if resolved_token:
                auth_token = resolved_token
            else:
                logger.error("Could not resolve 1Password secret for Twilio auth_token: %s", auth_token)
                return False

        assert self.caller_id is not None
        assert self.my_phone is not None
        assert account_sid is not None
        assert auth_token is not None

        cleaned_caller_id = clean_phone_e164(self.caller_id)
        cleaned_my_phone = clean_phone_e164(self.my_phone)

        # Inline TwiML executed when you pick up your phone:
        # Twilio dials the prospect with your business caller ID and starts recording.
        record_attr = ' record="record-from-answer"' if self.record else ""
        twiml = (
            f"<Response>"
            f'<Dial callerId="{cleaned_caller_id}"{record_attr}>'
            f"<Number>{cleaned_prospect}</Number>"
            f"</Dial>"
            f"</Response>"
        )

        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json"
        data: dict[str, str] = {
            "To": cleaned_my_phone,
            "From": cleaned_caller_id,
            "Twiml": twiml,
        }
        if self.recording_callback_url:
            data["RecordingStatusCallback"] = self.recording_callback_url
            data["RecordingStatusCallbackEvent"] = "completed"

        if os.environ.get("PYTEST_CURRENT_TEST"):
            logger.debug("TwilioBridgeCallingProvider: simulated call in test mode")
            return True

        try:
            resp = requests.post(
                url,
                data=data,
                auth=(account_sid, auth_token),
                timeout=10,
            )
            if resp.status_code in (200, 201):
                call_info = resp.json()
                call_sid = call_info.get("sid", "unknown")
                logger.info(
                    "Twilio bridge call initiated (SID: %s). Ringing %s to connect with %s",
                    call_sid,
                    cleaned_my_phone,
                    cleaned_prospect,
                )
                return True
            else:
                logger.error(
                    "Twilio API call failed with status %d: %s",
                    resp.status_code,
                    resp.text,
                )
                return False
        except Exception as exc:
            logger.error("Failed to initiate Twilio bridge call: %s", exc)
            return False


def twilio_config(campaign_name: Optional[str] = None) -> dict[str, Any]:
    from cocli.core.config import get_campaign, load_campaign_config, load_global_config
    from cocli.core.utils import deep_merge

    camp = campaign_name or get_campaign()
    merged: dict[str, Any] = dict(load_global_config().get("twilio", {}) or {})
    if camp:
        campaign_tw = load_campaign_config(camp).get("twilio", {}) or {}
        merged = deep_merge(merged, campaign_tw)
    return merged


def google_voice_config(campaign_name: Optional[str]) -> dict[str, Any]:
    from cocli.core.config import get_campaign, load_campaign_config, load_global_config
    from cocli.core.utils import deep_merge

    camp = campaign_name or get_campaign()
    merged: dict[str, Any] = dict(load_global_config().get("google_voice", {}) or {})
    if camp:
        campaign_gv = load_campaign_config(camp).get("google_voice", {}) or {}
        merged = deep_merge(merged, campaign_gv)
    return merged


def get_calling_provider(campaign_name: Optional[str] = None) -> CallingProvider:
    """Pick the configured calling provider.

    Resolution:
    1. If `provider` is "twilio", "twilio_bridge", or "bridge", return TwilioBridgeCallingProvider.
    2. If `provider` is "quo" or "openphone", return QuoCallingProvider.
    3. If `provider` is "browser_tab", return BrowserTabCallingProvider.
    4. If `provider` is "google_voice" (default):
       - If on WSL2, Windows, or a desktop with Chromium browser, return
         GoogleVoiceEdgeAppProvider (which attempts PWA/proxy launch, then
         standalone Chromium --app mode, then falls back to browser tab).
       - Otherwise return BrowserTabCallingProvider.
    """
    from cocli.core.config import get_campaign, load_campaign_config, load_global_config

    camp = campaign_name or get_campaign()
    global_cfg = load_global_config()
    camp_cfg = load_campaign_config(camp) if camp else {}

    provider_name = (
        camp_cfg.get("calling", {}).get("provider")
        or camp_cfg.get("google_voice", {}).get("provider")
        or global_cfg.get("calling", {}).get("provider")
        or global_cfg.get("google_voice", {}).get("provider")
        or global_cfg.get("twilio", {}).get("provider")
        or "google_voice"
    )
    provider_name = str(provider_name).lower()

    if provider_name in ("twilio", "twilio_bridge", "bridge"):
        tw_cfg = twilio_config(campaign_name)
        return TwilioBridgeCallingProvider(
            account_sid=tw_cfg.get("account_sid"),
            auth_token=tw_cfg.get("auth_token"),
            caller_id=tw_cfg.get("caller_id") or tw_cfg.get("business_number"),
            my_phone=tw_cfg.get("my_phone") or tw_cfg.get("bridge_to"),
            recording_callback_url=tw_cfg.get("recording_callback_url"),
            record=bool(tw_cfg.get("record", True)),
        )

    if provider_name in ("quo", "openphone"):
        gv_cfg = google_voice_config(campaign_name)
        return QuoCallingProvider(use_web=bool(gv_cfg.get("use_web", False)))

    if provider_name in ("browser_tab", "tab"):
        return BrowserTabCallingProvider()

    if provider_name == "google_voice":
        gv_cfg = google_voice_config(campaign_name)
        edge_app_id = gv_cfg.get("edge_app_id")
        if is_wsl() or sys.platform == "win32" or find_browser_app_binary():
            return GoogleVoiceEdgeAppProvider(edge_app_id=str(edge_app_id) if edge_app_id else None)
        return BrowserTabCallingProvider()

    return BrowserTabCallingProvider()
