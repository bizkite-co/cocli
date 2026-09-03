# POLICY: frictionless-data-policy-enforcement
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

from playwright.async_api import Browser, BrowserContext, Page

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


# SPA shells often survive the window `load` event as a white page plus a
# progress donut. Screenshot after goto(wait_until="load") races that paint.
_LOADER_GONE_AND_PAINTED = """() => {
  if (document.readyState !== 'complete' || !document.body) return false;
  if (document.fonts && document.fonts.status === 'loading') return false;

  const visible = (el) => {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || Number(s.opacity) === 0) {
      return false;
    }
    const r = el.getBoundingClientRect();
    return r.width > 8 && r.height > 8;
  };

  const loaders = document.querySelectorAll(
    '[aria-busy="true"], [role="progressbar"], [class*="spinner"], [class*="Spinner"], [class*="loader"], [class*="Loader"], [class*="preloader"], [class*="Preloader"], [class*="loading"], [class*="Loading"]'
  );
  for (const el of loaders) {
    if (visible(el)) return false;
  }

  const text = (document.body.innerText || '').replace(/\\s+/g, ' ').trim();
  if (/loading|please wait|just a (sec|moment)/i.test(text) && text.length < 40) {
    return false;
  }
  if (text.length >= 8) return true;

  const imgs = Array.from(document.images || []);
  return imgs.some((img) => img.complete && img.naturalWidth > 1 && visible(img));
}"""

_TWO_ANIMATION_FRAMES = """() => new Promise((resolve) => {
  requestAnimationFrame(() => requestAnimationFrame(() => resolve(true)));
})"""


async def wait_until_page_painted(page: Page, *, timeout_ms: int = 8000) -> None:
    """Hold until the viewport is more than a loading shell, then return.

    Never raises: a timed-out wait still lets the caller screenshot whatever
    is on screen. `networkidle` is capped because analytics/websockets often
    never go idle (same reason gm_scraper avoids it).
    """
    networkidle_ms = min(4000, timeout_ms)
    try:
        await page.wait_for_load_state("networkidle", timeout=networkidle_ms)
    except Exception:
        logger.debug("networkidle wait skipped or timed out before screenshot")

    try:
        await page.wait_for_function(_LOADER_GONE_AND_PAINTED, timeout=timeout_ms)
    except Exception:
        logger.debug("paint/loader wait timed out; screenshotting anyway")

    try:
        await page.evaluate(_TWO_ANIMATION_FRAMES)
    except Exception:
        logger.debug("animation-frame flush failed before screenshot")
