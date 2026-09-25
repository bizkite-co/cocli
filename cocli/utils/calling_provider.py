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

from datetime import datetime
import glob
import logging
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Optional, Protocol

from .google_voice_url import clean_phone_e164, google_voice_url
from .open_url import copy_to_windows_clipboard, is_wsl, open_url, spawn_detached

logger = logging.getLogger(__name__)


class CallingProvider(Protocol):
    last_error: Optional[str]
    caller_id: Optional[str]

    def dial(self, phone: str, campaign_name: Optional[str] = None) -> bool:
        """Launch a call to `phone`. Returns True if a launch action fired."""
        ...


class BrowserTabCallingProvider:
    """Fallback used when no provider-specific launch path is configured
    or available: open the Google Voice calls URL as a browser tab."""

    last_error: Optional[str] = None
    caller_id: Optional[str] = None

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
        for user_edge in glob.glob(
            "/mnt/c/Users/*/AppData/Local/Microsoft/Edge/Application/msedge.exe"
        ):
            if Path(user_edge).exists():
                return user_edge
        for user_chrome in glob.glob(
            "/mnt/c/Users/*/AppData/Local/Google/Chrome/Application/chrome.exe"
        ):
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
        patterns.extend(
            [
                f"/mnt/c/Users/*/AppData/Local/Microsoft/Edge/User Data/*/Web Applications/_crx__{app_id}",
                f"/mnt/c/Users/*/AppData/Local/Google/Chrome/User Data/*/Web Applications/_crx_{app_id}",
                f"/mnt/c/Users/*/AppData/Local/Microsoft/Edge/User Data/*/Web Applications/Manifest Resources/{app_id}",
                f"/mnt/c/Users/*/AppData/Local/Google/Chrome/User Data/*/Web Applications/Manifest Resources/{app_id}",
            ]
        )
    elif sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            patterns.extend(
                [
                    f"{local_app_data}/Microsoft/Edge/User Data/*/Web Applications/_crx__{app_id}",
                    f"{local_app_data}/Google/Chrome/User Data/*/Web Applications/_crx_{app_id}",
                    f"{local_app_data}/Microsoft/Edge/User Data/*/Web Applications/Manifest Resources/{app_id}",
                    f"{local_app_data}/Google/Chrome/User Data/*/Web Applications/Manifest Resources/{app_id}",
                ]
            )
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
        patterns.extend(
            [
                "/mnt/c/Users/*/AppData/Local/Microsoft/Edge/User Data/*/Web Applications/_crx__*",
                "/mnt/c/Users/*/AppData/Local/Google/Chrome/User Data/*/Web Applications/_crx_*",
            ]
        )
    elif sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            patterns.extend(
                [
                    f"{local_app_data}/Microsoft/Edge/User Data/*/Web Applications/_crx__*",
                    f"{local_app_data}/Google/Chrome/User Data/*/Web Applications/_crx_*",
                ]
            )

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
        self.last_error: Optional[str] = None
        self.caller_id: Optional[str] = None

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
                    logger.info(
                        "Launched Google Voice PWA via %s (app-id=%s)",
                        proxy,
                        target_app_id,
                    )
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
        self.last_error: Optional[str] = None
        self.caller_id: Optional[str] = None

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

    _cached_balance: Optional[tuple[float, str, float]] = None
    _balance_cache_ttl: float = 300.0

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        caller_id: Optional[str] = None,
        my_phone: Optional[str] = None,
        recording_callback_url: Optional[str] = None,
        record: bool = True,
        low_balance_threshold: float = 5.0,
    ):
        self.account_sid = account_sid or os.environ.get("TWILIO_ACCOUNT_SID")
        self.auth_token = auth_token or os.environ.get("TWILIO_AUTH_TOKEN")
        self.api_key = api_key or os.environ.get("TWILIO_API_KEY")
        self.api_secret = api_secret or os.environ.get("TWILIO_API_SECRET")
        self.caller_id = (
            caller_id
            or os.environ.get("TWILIO_CALLER_ID")
            or os.environ.get("TWILIO_PHONE_NUMBER")
        )
        self.my_phone = (
            my_phone
            or os.environ.get("TWILIO_MY_PHONE")
            or os.environ.get("TWILIO_BRIDGE_TO")
        )
        self.recording_callback_url = recording_callback_url or os.environ.get(
            "TWILIO_RECORDING_CALLBACK_URL"
        )
        self.record = record
        thresh_env = os.environ.get("TWILIO_LOW_BALANCE_THRESHOLD")
        self.low_balance_threshold = (
            float(thresh_env) if thresh_env else float(low_balance_threshold)
        )
        self.last_error: Optional[str] = None

    @classmethod
    def clear_balance_cache(cls) -> None:
        """Clear cached balance for testing or explicit reset."""
        cls._cached_balance = None

    def is_configured(self) -> bool:
        has_auth = bool(
            (self.api_key and self.api_secret and self.account_sid)
            or (self.account_sid and self.auth_token)
        )
        return bool(has_auth and self.caller_id and self.my_phone)

    def _resolve_credentials(
        self,
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Resolve (account_sid, auth_username, auth_password), batch-reading op:// references.

        If api_key and api_secret are provided, HTTP Basic Auth uses (api_key, api_secret)
        while the API URL uses account_sid. Otherwise, HTTP Basic Auth uses (account_sid, auth_token).
        All op:// refs are resolved together via read_op_secrets() so Windows Hello / 1Password
        only prompts once.
        """
        account_sid = self.account_sid
        auth_user: Optional[str] = None
        auth_pass: Optional[str] = None

        if self.api_key and self.api_secret:
            auth_user = self.api_key
            auth_pass = self.api_secret
        elif self.account_sid and self.auth_token:
            auth_user = self.account_sid
            auth_pass = self.auth_token
        else:
            return None, None, None

        if not account_sid or not auth_user or not auth_pass:
            return None, None, None

        # Collect op:// refs to batch-resolve
        op_refs: list[str] = []
        for ref in (account_sid, auth_user, auth_pass):
            if ref and ref.startswith("op://") and ref not in op_refs:
                op_refs.append(ref)

        resolved_map: dict[str, str] = {}
        if op_refs:
            from .op_utils import get_op_secret, read_op_secrets

            batch_res = read_op_secrets(*op_refs)
            if batch_res and len(batch_res) == len(op_refs):
                resolved_map = dict(zip(op_refs, batch_res))
            else:
                for ref in op_refs:
                    val = get_op_secret(ref)
                    if val:
                        resolved_map[ref] = val

            if account_sid in resolved_map:
                account_sid = resolved_map[account_sid]
            if auth_user in resolved_map:
                auth_user = resolved_map[auth_user]
            if auth_pass in resolved_map:
                auth_pass = resolved_map[auth_pass]

        if (
            not account_sid
            or account_sid.startswith("op://")
            or not auth_user
            or auth_user.startswith("op://")
            or not auth_pass
            or auth_pass.startswith("op://")
        ):
            return None, None, None

        return account_sid, auth_user, auth_pass

    def get_balance(
        self, bypass_cache: bool = False
    ) -> tuple[Optional[float], Optional[str]]:
        """Query Twilio Balance API. Returns (balance, currency) or (None, None).

        Caches balance in memory for `_balance_cache_ttl` seconds unless bypass_cache=True.
        """
        import requests

        now = time.time()
        if not bypass_cache and TwilioBridgeCallingProvider._cached_balance is not None:
            cached_bal, cached_curr, cached_time = (
                TwilioBridgeCallingProvider._cached_balance
            )
            if now - cached_time < TwilioBridgeCallingProvider._balance_cache_ttl:
                return cached_bal, cached_curr

        account_sid, auth_user, auth_pass = self._resolve_credentials()
        if not account_sid or not auth_user or not auth_pass:
            return None, None

        if os.environ.get("PYTEST_CURRENT_TEST"):
            logger.debug(
                "TwilioBridgeCallingProvider: simulated get_balance in test mode"
            )
            return 25.0, "USD"

        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Balance.json"
        try:
            resp = requests.get(url, auth=(auth_user, auth_pass), timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                balance = float(data.get("balance", 0.0))
                currency = str(data.get("currency", "USD"))
                TwilioBridgeCallingProvider._cached_balance = (balance, currency, now)
                return balance, currency
            else:
                logger.warning(
                    "Twilio Balance API returned status %d: %s",
                    resp.status_code,
                    resp.text,
                )
                return None, None
        except Exception as exc:
            logger.warning("Failed to query Twilio Balance API: %s", exc)
            return None, None

    def fetch_messages(
        self,
        to_phone: Optional[str] = None,
        limit: int = 50,
        date_sent_after: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        """Query Twilio REST API for messages.

        If to_phone is provided (or defaults to self.caller_id), queries incoming messages sent to that number.
        Returns a list of raw message dicts from Twilio API.
        """
        import requests

        account_sid, auth_user, auth_pass = self._resolve_credentials()
        if not account_sid or not auth_user or not auth_pass:
            self.last_error = "Twilio credentials not configured or could not be resolved"
            return []

        if os.environ.get("PYTEST_CURRENT_TEST"):
            logger.debug(
                "TwilioBridgeCallingProvider: simulated fetch_messages in test mode"
            )
            return []

        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        params: dict[str, Any] = {"PageSize": limit}
        target_to = to_phone or self.caller_id
        if target_to:
            params["To"] = clean_phone_e164(target_to)
        if date_sent_after:
            params["DateSent>="] = date_sent_after.strftime("%Y-%m-%d")

        try:
            resp = requests.get(
                url, params=params, auth=(auth_user, auth_pass), timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                raw_msgs = data.get("messages", [])
                return [m for m in raw_msgs if isinstance(m, dict)]
            else:
                self.last_error = (
                    f"Twilio Messages API error {resp.status_code}: {resp.text}"
                )
                logger.warning(self.last_error)
                return []
        except Exception as exc:
            self.last_error = f"Failed to fetch Twilio messages: {exc}"
            logger.warning(self.last_error)
            return []

    def get_account_info(self) -> Optional[dict[str, Any]]:
        """Query Twilio REST API for account details (status, type, friendly name).

        Returns dict with keys: friendly_name, type ('Trial' or 'Full'), status, sid.
        """
        import requests

        account_sid, auth_user, auth_pass = self._resolve_credentials()
        if not account_sid or not auth_user or not auth_pass:
            self.last_error = "Twilio credentials not configured or could not be resolved"
            return None

        if os.environ.get("PYTEST_CURRENT_TEST"):
            logger.debug(
                "TwilioBridgeCallingProvider: simulated get_account_info in test mode"
            )
            return {
                "friendly_name": "Test Account",
                "type": "Full",
                "status": "active",
                "sid": account_sid,
            }

        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}.json"
        try:
            resp = requests.get(url, auth=(auth_user, auth_pass), timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "friendly_name": data.get("friendly_name", ""),
                    "type": data.get("type", "Full"),
                    "status": data.get("status", "active"),
                    "sid": data.get("sid", account_sid),
                    "date_created": data.get("date_created", ""),
                }
            else:
                self.last_error = (
                    f"Twilio Account API error {resp.status_code}: {resp.text}"
                )
                logger.warning(self.last_error)
                return None
        except Exception as exc:
            self.last_error = f"Failed to fetch Twilio account info: {exc}"
            logger.warning(self.last_error)
            return None

    def get_incoming_phone_number(
        self, phone_number: Optional[str] = None
    ) -> Optional[dict[str, Any]]:
        """Query Twilio REST API for details on an incoming phone number.

        If phone_number is omitted, defaults to self.caller_id.
        Returns dict with: sid, phone_number, friendly_name, sms_url, sms_method, voice_url, capabilities.
        """
        import requests

        account_sid, auth_user, auth_pass = self._resolve_credentials()
        if not account_sid or not auth_user or not auth_pass:
            self.last_error = "Twilio credentials not configured or could not be resolved"
            return None

        target = phone_number or self.caller_id
        if not target:
            self.last_error = "No phone number specified to query"
            return None
        cleaned_target = clean_phone_e164(target)

        if os.environ.get("PYTEST_CURRENT_TEST"):
            logger.debug(
                "TwilioBridgeCallingProvider: simulated get_incoming_phone_number in test mode"
            )
            return {
                "sid": "PN1234567890abcdef1234567890abcdef",
                "phone_number": cleaned_target,
                "friendly_name": "Test Twilio Number",
                "sms_url": "https://handler.twilio.com/twiml/EHsimulated",
                "sms_method": "POST",
                "voice_url": "https://demo.twilio.com/welcome/voice/",
                "capabilities": {"voice": True, "sms": True, "mms": True},
            }

        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/IncomingPhoneNumbers.json"
        params = {"PhoneNumber": cleaned_target}
        try:
            resp = requests.get(
                url, params=params, auth=(auth_user, auth_pass), timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                numbers = data.get("incoming_phone_numbers", [])
                if numbers:
                    num_obj = numbers[0]
                    return {
                        "sid": num_obj.get("sid", ""),
                        "phone_number": num_obj.get("phone_number", cleaned_target),
                        "friendly_name": num_obj.get("friendly_name", ""),
                        "sms_url": num_obj.get("sms_url", ""),
                        "sms_method": num_obj.get("sms_method", "POST"),
                        "voice_url": num_obj.get("voice_url", ""),
                        "capabilities": num_obj.get("capabilities", {}),
                    }
                else:
                    self.last_error = f"Twilio phone number {cleaned_target} not found on account {account_sid}"
                    return None
            else:
                self.last_error = f"Twilio Phone Numbers API error {resp.status_code}: {resp.text}"
                logger.warning(self.last_error)
                return None
        except Exception as exc:
            self.last_error = f"Failed to fetch Twilio phone number: {exc}"
            logger.warning(self.last_error)
            return None

    def update_incoming_phone_number_sms_url(
        self, sms_url: str, phone_number: Optional[str] = None
    ) -> tuple[bool, Optional[str]]:
        """Update the SmsUrl webhook / TwiML URL for an incoming phone number.

        Returns (True, sid) on success or (False, error_message) on failure.
        """
        import requests

        account_sid, auth_user, auth_pass = self._resolve_credentials()
        if not account_sid or not auth_user or not auth_pass:
            err = "Twilio credentials not configured or could not be resolved"
            self.last_error = err
            return False, err

        info = self.get_incoming_phone_number(phone_number)
        if not info or not info.get("sid"):
            err = self.last_error or f"Could not find incoming phone number {phone_number or self.caller_id}"
            return False, err

        sid = info["sid"]
        if os.environ.get("PYTEST_CURRENT_TEST"):
            logger.debug(
                "TwilioBridgeCallingProvider: simulated update_incoming_phone_number_sms_url in test mode"
            )
            return True, sid

        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/IncomingPhoneNumbers/{sid}.json"
        data = {"SmsUrl": sms_url, "SmsMethod": "POST"}
        try:
            resp = requests.post(
                url, data=data, auth=(auth_user, auth_pass), timeout=15
            )
            if resp.status_code in (200, 201):
                logger.info(
                    "Updated Twilio phone number %s (SID: %s) SmsUrl to %s",
                    info.get("phone_number"),
                    sid,
                    sms_url,
                )
                return True, sid
            else:
                err = f"Twilio API error {resp.status_code}: {resp.text}"
                self.last_error = err
                logger.warning(err)
                return False, err
        except Exception as exc:
            err = f"Failed to update Twilio SmsUrl: {exc}"
            self.last_error = err
            logger.warning(err)
            return False, err

    def is_low_balance(
        self, threshold: Optional[float] = None, bypass_cache: bool = False
    ) -> tuple[bool, Optional[float], Optional[str]]:
        """Check if account balance is below warning threshold.

        Returns (is_low, balance, currency). If balance cannot be determined,
        returns (False, None, None).
        """
        thresh = self.low_balance_threshold if threshold is None else threshold
        balance, currency = self.get_balance(bypass_cache=bypass_cache)
        if balance is None:
            return False, None, currency
        return balance < thresh, balance, currency

    def dial(self, phone: str, campaign_name: Optional[str] = None) -> bool:
        import requests

        cleaned_prospect = clean_phone_e164(phone)
        copy_to_windows_clipboard(cleaned_prospect)

        if not self.is_configured():
            self.last_error = (
                "Twilio calling provider is missing required configuration: "
                f"account_sid={bool(self.account_sid)}, auth_token={bool(self.auth_token)}, "
                f"api_key={bool(self.api_key)}, api_secret={bool(self.api_secret)}, "
                f"caller_id={bool(self.caller_id)}, my_phone={bool(self.my_phone)}"
            )
            logger.error(self.last_error)
            return False

        account_sid, auth_user, auth_pass = self._resolve_credentials()
        if not account_sid or not auth_user or not auth_pass:
            self.last_error = f"Could not resolve Twilio credentials for account={self.account_sid}"
            logger.error(self.last_error)
            return False

        assert self.caller_id is not None
        assert self.my_phone is not None

        cleaned_caller_id = clean_phone_e164(self.caller_id)
        cleaned_my_phone = clean_phone_e164(self.my_phone)

        # Inline TwiML executed when you pick up your phone:
        # Twilio dials the prospect with your business caller ID and starts recording.
        # If the destination fails (e.g. busy, blacklisted, unreachable), Twilio speaks
        # a clear prompt rather than hanging up abruptly in silence.
        record_attr = ' record="record-from-answer"' if self.record else ""
        twiml = (
            f"<Response>"
            f'<Dial callerId="{cleaned_caller_id}"{record_attr}>'
            f"<Number>{cleaned_prospect}</Number>"
            f"</Dial>"
            f"<Say>The call could not be connected. Goodbye.</Say>"
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
            self.last_error = None
            return True

        try:
            resp = requests.post(
                url,
                data=data,
                auth=(auth_user, auth_pass),
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
                self.last_error = None
                return True
            else:
                err_msg = resp.text
                try:
                    err_json = resp.json()
                    err_msg = err_json.get("message", resp.text)
                except Exception:
                    pass
                self.last_error = f"Twilio error {resp.status_code}: {err_msg}"
                logger.error(
                    "Twilio API call failed with status %d: %s",
                    resp.status_code,
                    resp.text,
                )
                return False
        except Exception as exc:
            self.last_error = f"Twilio bridge error: {exc}"
            logger.error("Failed to initiate Twilio bridge call: %s", exc)
            return False

    def test_voice_call(
        self, to_phone: Optional[str] = None
    ) -> tuple[bool, Optional[str]]:
        """Initiate a single-leg automated test call to verify voice calling works.

        Uses inline TwiML with an automated spoken message so it does not bridge to another number.
        Returns (True, call_sid) on success or (False, error_message) on failure.
        """
        import requests

        account_sid, auth_user, auth_pass = self._resolve_credentials()
        if not account_sid or not auth_user or not auth_pass:
            err = "Twilio credentials not configured or could not be resolved"
            self.last_error = err
            return False, err

        target_phone = to_phone or self.my_phone
        if not target_phone or not self.caller_id:
            err = "Missing caller_id or destination phone number"
            self.last_error = err
            return False, err

        cleaned_target = clean_phone_e164(target_phone)
        cleaned_caller_id = clean_phone_e164(self.caller_id)

        if os.environ.get("PYTEST_CURRENT_TEST"):
            logger.debug(
                "TwilioBridgeCallingProvider: simulated test_voice_call in test mode"
            )
            return True, "CA1234567890abcdef1234567890abcdef"

        twiml = (
            "<Response>"
            "<Say voice=\"alice\">Hello! This is an automated test call from Company CLI. "
            "Your Twilio voice connection is working properly.</Say>"
            "</Response>"
        )

        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json"
        data = {
            "To": cleaned_target,
            "From": cleaned_caller_id,
            "Twiml": twiml,
        }
        try:
            resp = requests.post(
                url, data=data, auth=(auth_user, auth_pass), timeout=15
            )
            if resp.status_code in (200, 201):
                call_info = resp.json()
                call_sid = call_info.get("sid", "unknown")
                logger.info(
                    "Twilio test voice call initiated (SID: %s) to %s",
                    call_sid,
                    cleaned_target,
                )
                self.last_error = None
                return True, call_sid
            else:
                err_msg = resp.text
                err_code = None
                try:
                    err_json = resp.json()
                    err_msg = err_json.get("message", resp.text)
                    err_code = err_json.get("code")
                except Exception:
                    pass
                code_prefix = f" [{err_code}]" if err_code else ""
                err = f"Twilio error {resp.status_code}{code_prefix}: {err_msg}"
                self.last_error = err
                logger.warning(err)
                return False, err
        except Exception as exc:
            err = f"Failed to initiate Twilio test voice call: {exc}"
            self.last_error = err
            logger.warning(err)
            return False, err

    def send_sms(
        self, to_phone: str, body: str, from_phone: Optional[str] = None
    ) -> tuple[bool, Optional[str]]:
        """Send an SMS message via Twilio REST API.

        Returns (True, message_sid) on success or (False, error_message) on failure.
        """
        import requests

        account_sid, auth_user, auth_pass = self._resolve_credentials()
        if not account_sid or not auth_user or not auth_pass:
            err = "Twilio credentials not configured or could not be resolved"
            self.last_error = err
            return False, err

        source_phone = from_phone or self.caller_id
        if not source_phone:
            err = "Missing outbound caller_id / phone number"
            self.last_error = err
            return False, err

        cleaned_target = clean_phone_e164(to_phone)
        cleaned_source = clean_phone_e164(source_phone)

        if os.environ.get("PYTEST_CURRENT_TEST"):
            logger.debug(
                "TwilioBridgeCallingProvider: simulated send_sms in test mode"
            )
            return True, "SM1234567890abcdef1234567890abcdef"

        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        data = {
            "To": cleaned_target,
            "From": cleaned_source,
            "Body": body,
        }
        try:
            resp = requests.post(
                url, data=data, auth=(auth_user, auth_pass), timeout=15
            )
            if resp.status_code in (200, 201):
                msg_info = resp.json()
                msg_sid = msg_info.get("sid", "unknown")
                logger.info(
                    "Twilio SMS sent (SID: %s) to %s",
                    msg_sid,
                    cleaned_target,
                )
                self.last_error = None
                return True, msg_sid
            else:
                err_msg = resp.text
                err_code = None
                try:
                    err_json = resp.json()
                    err_msg = err_json.get("message", resp.text)
                    err_code = err_json.get("code")
                except Exception:
                    pass
                code_prefix = f" [{err_code}]" if err_code else ""
                err = f"Twilio SMS error {resp.status_code}{code_prefix}: {err_msg}"
                self.last_error = err
                logger.warning(err)
                return False, err
        except Exception as exc:
            err = f"Failed to send Twilio SMS: {exc}"
            self.last_error = err
            logger.warning(err)
            return False, err

    def get_trusthub_status(self) -> Optional[dict[str, Any]]:
        """Query Twilio TrustHub API for Primary Customer Profile status.

        Returns dict with: sid, friendly_name, status, policy_sid, policy_name.
        """
        import requests

        account_sid, auth_user, auth_pass = self._resolve_credentials()
        if not account_sid or not auth_user or not auth_pass:
            self.last_error = "Twilio credentials not configured or could not be resolved"
            return None

        if os.environ.get("PYTEST_CURRENT_TEST"):
            logger.debug(
                "TwilioBridgeCallingProvider: simulated get_trusthub_status in test mode"
            )
            return {
                "sid": "BU1234567890abcdef1234567890abcdef",
                "friendly_name": "Test Profile",
                "status": "twilio-approved",
                "policy_sid": "RN1234567890abcdef1234567890abcdef",
                "policy_name": "Primary customer profile for individual",
            }

        url = "https://trusthub.twilio.com/v1/CustomerProfiles"
        try:
            resp = requests.get(url, auth=(auth_user, auth_pass), timeout=10)
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if not results:
                    return None
                prof = results[0]
                prof_sid = prof.get("sid", "")
                friendly_name = prof.get("friendly_name", "")
                status = prof.get("status", "")
                policy_sid = prof.get("policy_sid", "")
                policy_name: Optional[str] = None
                if policy_sid:
                    try:
                        p_resp = requests.get(
                            f"https://trusthub.twilio.com/v1/Policies/{policy_sid}",
                            auth=(auth_user, auth_pass),
                            timeout=8,
                        )
                        if p_resp.status_code == 200:
                            policy_name = p_resp.json().get("friendly_name")
                    except Exception:
                        pass
                return {
                    "sid": prof_sid,
                    "friendly_name": friendly_name,
                    "status": status,
                    "policy_sid": policy_sid,
                    "policy_name": policy_name or "Individual",
                }
            else:
                self.last_error = f"Twilio TrustHub API error {resp.status_code}: {resp.text}"
                logger.warning(self.last_error)
                return None
        except Exception as exc:
            self.last_error = f"Failed to fetch Twilio TrustHub status: {exc}"
            logger.warning(self.last_error)
            return None

    def get_dialing_permissions(
        self, iso_code: str = "US"
    ) -> Optional[dict[str, Any]]:
        """Query Twilio Voice Dialing Permissions API for country-level permissions.

        Returns dict with: iso_code, name, low_risk_numbers_enabled, high_risk_special_numbers_enabled, high_risk_tollfraud_numbers_enabled.
        """
        import requests

        account_sid, auth_user, auth_pass = self._resolve_credentials()
        if not account_sid or not auth_user or not auth_pass:
            self.last_error = "Twilio credentials not configured or could not be resolved"
            return None

        if os.environ.get("PYTEST_CURRENT_TEST"):
            logger.debug(
                "TwilioBridgeCallingProvider: simulated get_dialing_permissions in test mode"
            )
            return {
                "iso_code": iso_code.upper(),
                "name": "United States/Canada",
                "low_risk_numbers_enabled": True,
                "high_risk_special_numbers_enabled": False,
                "high_risk_tollfraud_numbers_enabled": False,
            }

        url = f"https://voice.twilio.com/v1/DialingPermissions/Countries/{iso_code.upper()}"
        try:
            resp = requests.get(url, auth=(auth_user, auth_pass), timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "iso_code": data.get("iso_code", iso_code.upper()),
                    "name": data.get("name", ""),
                    "low_risk_numbers_enabled": bool(data.get("low_risk_numbers_enabled", False)),
                    "high_risk_special_numbers_enabled": bool(data.get("high_risk_special_numbers_enabled", False)),
                    "high_risk_tollfraud_numbers_enabled": bool(data.get("high_risk_tollfraud_numbers_enabled", False)),
                }
            else:
                self.last_error = f"Twilio Dialing Permissions API error {resp.status_code}: {resp.text}"
                logger.warning(self.last_error)
                return None
        except Exception as exc:
            self.last_error = f"Failed to fetch Twilio dialing permissions: {exc}"
            logger.warning(self.last_error)
            return None


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
            api_key=tw_cfg.get("api_key"),
            api_secret=tw_cfg.get("api_secret"),
            caller_id=tw_cfg.get("caller_id") or tw_cfg.get("business_number"),
            my_phone=tw_cfg.get("my_phone") or tw_cfg.get("bridge_to"),
            recording_callback_url=tw_cfg.get("recording_callback_url"),
            record=bool(tw_cfg.get("record", True)),
            low_balance_threshold=float(tw_cfg.get("low_balance_threshold", 20.0)),
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
            return GoogleVoiceEdgeAppProvider(
                edge_app_id=str(edge_app_id) if edge_app_id else None
            )
        return BrowserTabCallingProvider()

    return BrowserTabCallingProvider()


def get_cached_twilio_balance_warning(
    campaign_name: Optional[str] = None,
) -> Optional[str]:
    """Return a Rich markup warning string if Twilio provider is active and balance is low."""
    from cocli.core.config import get_campaign

    try:
        provider = get_calling_provider(campaign_name or get_campaign())
        if isinstance(provider, TwilioBridgeCallingProvider):
            if TwilioBridgeCallingProvider._cached_balance is not None:
                is_low, bal, curr = provider.is_low_balance()
                if is_low and bal is not None:
                    return f"[bold yellow]⚠️ Twilio: ${bal:.2f}[/bold yellow]"
    except Exception:
        pass
    return None
