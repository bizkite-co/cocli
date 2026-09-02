# POLICY: frictionless-data-policy-enforcement
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

from playwright.async_api import Browser, BrowserContext

from .headers import ANTI_BOT_HEADERS, USER_AGENT

logger = logging.getLogger(__name__)

_STEALTH_INIT_SCRIPT = (Path(__file__).parent / "stealth_init.js").read_text()

_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
]


async def launch_browser(playwright: Any, *, headless: bool = True) -> Browser:
    """Same Chromium launch the Pi workers use (Edge channel when available)."""
    try:
        return cast(
            Browser,
            await playwright.chromium.launch(
                headless=headless, channel="msedge", args=_LAUNCH_ARGS
            ),
        )
    except Exception:
        return cast(
            Browser,
            await playwright.chromium.launch(headless=headless, args=_LAUNCH_ARGS),
        )


async def new_details_context(browser: Browser) -> BrowserContext:
    """Google Maps details context: UA + headers. Matches run_details_worker."""
    context = await browser.new_context(
        user_agent=USER_AGENT, extra_http_headers=ANTI_BOT_HEADERS
    )
    await setup_optimized_context(context)
    return context


async def new_enrichment_context(browser: Browser) -> BrowserContext:
    """Website enrichment context: UA + headers + stealth. Matches run_enrichment_worker."""
    context = await browser.new_context(
        user_agent=USER_AGENT, extra_http_headers=ANTI_BOT_HEADERS
    )
    await setup_stealth_context(context)
    return context


async def setup_stealth_context(
    context: BrowserContext,
) -> None:
    """
    Applies absolute high-fidelity anti-bot measures to a Playwright context.
    Uses centralized project ANTI_BOT_HEADERS.
    """
    # 1. Comprehensive Stealth Script (Fingerprint Masking)
    await context.add_init_script(_STEALTH_INIT_SCRIPT)

    # 2. Set Centralized Extra Headers
    await context.set_extra_http_headers(ANTI_BOT_HEADERS)

async def setup_optimized_context(
    context: BrowserContext, 
) -> None:
    """
    No-op for maximum fidelity. 
    Efficiency considerations are strictly prohibited during this troubleshooting phase.
    """
    pass
