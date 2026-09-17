"""Pluggable "how do we actually launch a call" abstraction.

Google Voice's web UI has no stable way to route a dial into an existing
browser window - plain open_url() always lands in a new tab of whatever
the default browser is, forcing manual tab-switching mid-call (Mark,
2026-09-16). On Windows/WSL2, Edge's *installed PWA* for Google Voice has
a real single-instance launch path (msedge_proxy.exe --app-id=...,
confirmed against the sibling "Google Messages" PWA's own Start Menu
shortcut), but that mechanism is entirely Edge/Windows/Google-Voice
specific. Mark is also evaluating other providers (e.g. "Quo Business
Plan") that would need a completely different launch mechanism, so
provider-specific launch logic lives behind CallingProvider instead of
being hardcoded into open_url.py/company_detail.py.

To add a provider: implement CallingProvider.dial() and add a branch in
get_calling_provider()'s dispatch on the configured `provider` name.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Optional, Protocol

from .google_voice_url import google_voice_url
from .open_url import is_wsl, open_url, spawn_detached

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


class GoogleVoiceEdgeAppProvider:
    """Windows/WSL2 only: launch (or reuse, since PWAs are single-instance)
    the installed Google Voice Edge app instead of opening a browser tab.

    `edge_app_id` is a per-machine value - Edge assigns a random 32-char
    hex id per installed PWA, not portable between machines or users - so
    it must come from the local, non-synced `cocli_config.toml`
    (`[google_voice] edge_app_id = "..."`), never from a campaign's
    config.toml (that file is shared/synced cocli_data and would carry
    the wrong id, or none, onto every other machine that reads it).
    """

    def __init__(self, edge_app_id: str):
        self.edge_app_id = edge_app_id

    def dial(self, phone: str, campaign_name: Optional[str] = None) -> bool:
        proxy = find_msedge_proxy()
        if not proxy:
            logger.warning("msedge_proxy.exe not found; falling back to browser tab")
            return BrowserTabCallingProvider().dial(phone, campaign_name)
        # Only --profile-directory and --app-id are confirmed (2026-09-16
        # manual test: launching with exactly these two flags opened the
        # correct, single-instance Google Voice PWA window). An earlier
        # version of this also passed --app-url=<dial url>, guessed from
        # the *install-time* shortcut of a sibling PWA rather than
        # verified against a real launch - that guess was wrong: it made
        # msedge_proxy.exe fall back to a plain browser tab instead of the
        # PWA window (2026-09-17, Mark). Until a real way to pre-fill the
        # number is confirmed, this only focuses/opens the PWA - the
        # number still needs to be typed in manually.
        command = [
            proxy,
            "--profile-directory=Default",
            f"--app-id={self.edge_app_id}",
        ]
        if spawn_detached(command):
            return True
        return BrowserTabCallingProvider().dial(phone, campaign_name)


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

    `[google_voice] edge_app_id` lives in the machine-local
    `cocli_config.toml` (see GoogleVoiceEdgeAppProvider docstring); when
    it's set and we're on WSL2/Windows, prefer the single-instance PWA
    launch. Otherwise fall back to today's plain-tab behavior.
    """
    gv_cfg = google_voice_config(campaign_name)
    edge_app_id = gv_cfg.get("edge_app_id")
    provider_name = gv_cfg.get("provider", "google_voice")

    if provider_name == "google_voice" and edge_app_id and is_wsl():
        return GoogleVoiceEdgeAppProvider(str(edge_app_id))
    return BrowserTabCallingProvider()
