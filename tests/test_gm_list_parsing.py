# POLICY: frictionless-data-policy-enforcement
"""Live sanity check: is Google Maps still returning what we expect?

Scraping is inherently fragile - Google can change their HTML at any time,
with no warning, independent of anything we control. This test is not a
parser-regression test (see tests/unit/test_google_maps_parser.py for that,
which checks our parser against frozen HTML snapshots and is immune to
Google changing anything live). This one intentionally hits live Google
Maps, through the exact real production Navigator + SidebarScraper.scrape()
path (same scrolling, hydration, and now periodic block-detection our
workers use), for a handful of long-lived locations - well-known national
chains, in dense metro areas, chosen so the expected businesses are very
unlikely to disappear over a ~10 year horizon - and asserts each shows up
somewhere in the results with a plausible review count/rating. If Google
has changed their HTML out from under our parser, or a location starts
getting blocked/rate-limited, this fails fast and specifically instead of
the parser silently degrading in production.

Previously (until 2026-08-17) this test hardcoded a single fixed lat/lon
(34.2499, -118.2605 - the same regression coordinate that was hardcoded
into Navigator.goto()'s production home_url, see task-agent ticket
regression-gm-list-stuck-at-60-for-months-broken-stealth-script-and-no-backoff-on-google-block-detection),
only looked at the first unscrolled batch of results, and never actually
asserted against ground_truth.json's own `expectations` field - it only
checked "did we find *any* rated business," which would pass even if the
specific chains Google used to return had vanished from the results
entirely. Now genuinely parametrized per location, using each location's
own coordinates, scrolling for real via SidebarScraper.scrape() (a national
chain often isn't in the first unscrolled page - confirmed live: an
earlier single-page version of this test found AutoZone with an
unhydrated review count, and found no Starbucks/Home Depot at all in the
first ~8 results for Seattle/NYC), with per-expectation name/review/rating
assertions against the real parsed items.

Real finding from building this, confirmed live 2026-08-17: a specific
national chain is NOT guaranteed to appear in a generic category search,
even in a dense metro area with that chain present (confirmed: no
Starbucks in 69 fully-scrolled "coffee" results for downtown Seattle; no
Home Depot in 67 fully-scrolled "hardware store" results for Midtown
Manhattan - Google's relevance ranking favors locally-relevant results
over ubiquity). Only assert a specific name_regex where you've confirmed
it's reliable (AutoZone/O'Reilly near LA); otherwise use the aggregate
(no name_regex) expectation form.

(An earlier revision of this file also reported reviews_count coming back
None for 100% of results and floated a parser-regression theory - that
was wrong, and was actually a bug in this file's own browser context
setup, missing the user_agent/extra_http_headers production always sets.
See the comment on _fetch_live_items below for the corrected story.)
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import pytest
from playwright.async_api import async_playwright

from cocli.scrapers.google.gm_scraper.navigator import Navigator
from cocli.scrapers.google.gm_scraper.scanner import SidebarScraper
from cocli.utils.alert_utils import check_and_alert_google_maps_block
from cocli.utils.async_iteration import iterate_with_idle_timeout

GROUND_TRUTH_DIR = Path("tests/data/maps.google.com")
JSON_PATH = GROUND_TRUTH_DIR / "ground_truth.json"
CACHE_DIR = GROUND_TRUTH_DIR / "ground_truth"
STALE_AFTER = timedelta(days=7)

# Bounds for the live scroll/scan, mirroring worker_service.py's
# SCRAPE_IDLE_TIMEOUT_S/SCRAPE_ABSOLUTE_TIMEOUT_S but tighter - this is a
# sanity check that should fail fast, not a production discovery task.
SCAN_IDLE_TIMEOUT_S = 20
SCAN_ABSOLUTE_TIMEOUT_S = 180


def _load_locations() -> List[Dict[str, Any]]:
    if not JSON_PATH.exists():
        return []
    with open(JSON_PATH, "r") as f:
        truth = json.load(f)
    locations: List[Dict[str, Any]] = truth.get("locations", [])
    return locations


def _location_ids(location: Dict[str, Any]) -> str:
    return str(location.get("name", "unknown"))


async def _fetch_live_items(lat: float, lon: float, query: str) -> List[Dict[str, Any]]:
    """Runs the real production Navigator + SidebarScraper.scrape() against
    live Google Maps (real scrolling/hydration/periodic block-detection,
    no tile_id so the tile-bounds filter and early-stop logic are inert -
    a ground-truth check wants the full unfiltered result set) and returns
    each item's name/reviews/rating as plain dicts, ready to cache as JSON."""
    from cocli.utils.headers import ANTI_BOT_HEADERS, USER_AGENT
    from cocli.utils.playwright_utils import setup_stealth_context

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Must match worker_service.py's real context setup exactly
        # (user_agent + extra_http_headers) - confirmed live 2026-08-17:
        # without these two, reviews_count came back None for 100% of
        # results (0/48, even for turboship's own real category/location
        # that had good production data hours earlier) while
        # average_rating stayed populated. Adding them alone took it to
        # 54/61 (88.5%), matching `cocli data metrics`' real historical
        # 92.3%. This was a test-harness bug, not a production regression
        # or a category-specific Google rendering difference - the
        # "Finding 2: reviews_count gap" write-up in this file's earlier
        # revision (and the task-agent ticket) was wrong; corrected here.
        context = await browser.new_context(
            viewport={"width": 1280, "height": 1024},
            user_agent=USER_AGENT,
            extra_http_headers=ANTI_BOT_HEADERS,
        )

        await setup_stealth_context(context)

        page = await context.new_page()
        nav = Navigator(page)

        success = await nav.goto(lat, lon, 2.0, 1.0, query=query)
        assert success, f"Production Human navigation flow failed for query {query!r} at ({lat}, {lon})."

        was_blocked = await check_and_alert_google_maps_block(
            page, f"Ground-truth sanity check for query {query!r} at ({lat}, {lon})"
        )
        assert not was_blocked, (
            f"Google Maps block/CAPTCHA detected while running ground-truth check "
            f"for query {query!r} at ({lat}, {lon}) - can't distinguish a real "
            "parser regression from a rate-limit right now."
        )

        scraper = SidebarScraper(page)
        items: List[Dict[str, Any]] = []
        try:
            async for item in iterate_with_idle_timeout(
                scraper.scrape(
                    search_string=query,
                    processed_place_ids=set(),
                    force_refresh=False,
                    ttl_days=30,
                    tile_id=None,
                ),
                idle_timeout_s=SCAN_IDLE_TIMEOUT_S,
                absolute_timeout_s=SCAN_ABSOLUTE_TIMEOUT_S,
            ):
                items.append(
                    {
                        "name": str(item.name) if item.name is not None else None,
                        "reviews_count": item.reviews_count,
                        "average_rating": item.average_rating,
                    }
                )
        except TimeoutError:
            # Covers both IdleTimeoutError (no new item for
            # SCAN_IDLE_TIMEOUT_S) and the bare TimeoutError
            # iterate_with_idle_timeout raises on the absolute deadline -
            # keep whatever was found before either tripped.
            pass

        await browser.close()
        return items


@pytest.mark.asyncio
@pytest.mark.parametrize("location", _load_locations(), ids=_location_ids)
async def test_ground_truth_location_still_returns_expected_results(location: Dict[str, Any]) -> None:
    name = location["name"]
    lat = float(location["lat"])
    lon = float(location["lon"])
    query = location["query"]
    min_results = location.get("min_results", 1)
    expectations = location.get("expectations", [])

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{name}.json"

    is_stale = (
        not cache_path.exists()
        or (datetime.now(UTC) - datetime.fromtimestamp(cache_path.stat().st_mtime, tz=UTC)) > STALE_AFTER
    )

    if is_stale:
        items = await _fetch_live_items(lat, lon, query)
        cache_path.write_text(json.dumps(items, indent=2), encoding="utf-8")
    else:
        items = json.loads(cache_path.read_text(encoding="utf-8"))

    assert len(items) >= min_results, (
        f"[{name}] Expected at least {min_results} results for query {query!r}, "
        f"got {len(items)}. Google may have changed their HTML, or this "
        "location/query is no longer returning what it used to."
    )

    for expectation in expectations:
        name_regex = expectation.get("name_regex")
        min_reviews = expectation.get("min_reviews", 0)
        min_rating = expectation.get("min_rating", 0.0)

        def _meets_bar(item: Dict[str, Any]) -> bool:
            reviews = item.get("reviews_count") or 0
            rating = item.get("average_rating") or 0.0
            return bool(reviews >= min_reviews and rating >= min_rating)

        if name_regex is not None:
            # Named-chain form: this specific business must appear AND meet
            # the bar. Proven reliable for national chains in dense areas
            # (e.g. AutoZone/O'Reilly near LA) - confirmed live 2026-08-17.
            # NOT reliable for every chain/city combo: a live run against
            # Starbucks near downtown Seattle and Home Depot near Midtown
            # Manhattan found neither in 65-70 real, fully-scrolled results -
            # Google's relevance ranking for a generic category search
            # doesn't guarantee a specific chain surfaces, even a ubiquitous
            # one. Use the aggregate form (below) unless you've confirmed a
            # specific chain reliably appears for that location/query.
            import re

            pattern = re.compile(name_regex, re.IGNORECASE)
            match = next(
                (item for item in items if pattern.search(str(item.get("name") or ""))),
                None,
            )
            assert match is not None, (
                f"[{name}] Expected a business matching {name_regex!r} among "
                f"{len(items)} results for query {query!r}, but none of "
                f"{[item.get('name') for item in items]} matched. Google may have "
                "changed their HTML, or this chain is no longer showing up for "
                "this search - either way, our pipeline needs a look."
            )
            assert _meets_bar(match), (
                f"[{name}] {match.get('name')} has {match.get('reviews_count')} reviews "
                f"(expected >= {min_reviews}) and rating {match.get('average_rating')} "
                f"(expected >= {min_rating})."
            )
        else:
            # Aggregate form: no specific chain required - at least one of
            # the real results found must meet the bar. Chain-agnostic, so
            # it survives normal ranking fluctuation; still fails fast if
            # the pipeline is genuinely broken/blocked (nothing well-formed
            # comes back at all).
            assert any(_meets_bar(item) for item in items), (
                f"[{name}] Expected at least one of {len(items)} results for query "
                f"{query!r} to have >= {min_reviews} reviews and >= {min_rating} rating, "
                f"but none did: {items}"
            )
