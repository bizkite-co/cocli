# cocli/utils/headers.py

"""
Centralized headers to prevent bot detection and maintain consistent scraping behavior.
"""

import random


def jittered_delay_ms(base_ms: int, jitter_pct: float = 0.4) -> int:
    """Randomizes a fixed anti-bot pacing delay within +/-jitter_pct of base_ms.

    A script that waits exactly the same number of milliseconds before
    every single action, forever, is itself a detectable behavioral
    fingerprint - real interaction timing always has natural variance.
    Use this for deliberate pacing delays (page.wait_for_timeout calls
    between scroll/click actions); do NOT use it for wait_for(timeout=...)
    budgets, which are a "how long to wait for an element" ceiling, not a
    pacing delay - randomizing those trades reliability for no anti-bot
    benefit.
    """
    spread = base_ms * jitter_pct
    return round(random.uniform(base_ms - spread, base_ms + spread))

# Must match the ACTUAL Chromium build Playwright launches (checked via
# `browser.version` - currently 140.x), not an arbitrary "current" number
# or a real user's own browser version copied from a HAR. Claiming a
# version the underlying engine doesn't match is itself a detectable
# inconsistency (client hints, JS feature support) - worse than being
# merely stale (Mark, 2026-09-17: alliedwealth.com SiteGround bot
# challenge investigation found this constant 20 major versions behind
# current browsers; matching the real engine version is the safe fix,
# not chasing whatever version a real browser happens to report).
CHROME_VERSION = "140"

USER_AGENT = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{CHROME_VERSION}.0.0.0 Safari/537.36"

# Browser-like headers to reduce shadow ban risk.
#
# 2026-09-17 (alliedwealth.com investigation): recorded our own scraper's
# actual outgoing request via Playwright's record_har_path and diffed it
# field-by-field against Mark's real-browser HAR for the same site.
# Two concrete, confirmed differences fixed here:
#   - DNT: 1 - we were sending this; the real browser sent NO DNT header
#     at all. Modern Chrome/Edge don't send Do Not Track by default -
#     sending it ourselves is a "trying too hard" tell that a genuine,
#     unmodified browser install wouldn't produce.
#   - Accept-Encoding was missing zstd - the real browser advertised
#     "gzip, deflate, br, zstd"; Playwright's bundled Chromium (140.x)
#     supports decoding zstd natively, so there's no risk in advertising
#     it, only a mismatch in NOT advertising it.
ANTI_BOT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Sec-Ch-Ua": f'"Chromium";v="{CHROME_VERSION}", "Not(A:Brand";v="24", "Google Chrome";v="{CHROME_VERSION}"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}
