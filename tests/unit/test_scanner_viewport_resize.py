"""Guards SidebarScraper.scrape()'s viewport-drift detection (scanner.py).

Google auto-resizes/recenters/zooms-out the map for sparse tiles (e.g. over
open ocean or a large desert) to keep finding listings for the infinite-
scroll feed - and does this progressively AS THE SCAN SCROLLS, not only once
at initial load. The per-item tile-bounds filter already discards results
from outside the tile one-by-one, but each one still looks like "new" DOM
content to the stall-detector, so the scan loop used to run the full 90s
idle-timeout instead of failing fast.

Regression history: the first version of this check (2026-08-07) ran once,
up front, comparing only the center point against tile bounds. Confirmed
live 2026-08-16 that this was insufficient two ways at once: (1) center-only
- a zoomed-out view can keep its center technically inside the tile while
the actual visible search area covers far more than the tile; (2) checked-
once - drift that develops mid-scroll, after the one-time initial check
already passed, was never caught. A real production scan ran 5+ minutes,
parsing ~90 real listings, all discarded, before either fix landed. These
tests guard both: a static out-of-bounds/low-zoom URL still short-circuits
immediately (regression coverage for the original fix), AND a URL that
starts in-bounds but drifts only on a later check (simulating mid-scroll
drift) still stops the loop rather than continuing to scan discarded
content.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from cocli.scrapers.google.gm_scraper.scanner import SidebarScraper

TILE_ID = "18.1_-66.1"  # bounds: lat [18.1, 18.2), lon [-66.1, -66.0)


def _make_page(url: str) -> MagicMock:
    page = MagicMock()
    page.is_closed.return_value = False
    page.url = url
    page.wait_for_selector = AsyncMock(return_value=None)
    page.wait_for_timeout = AsyncMock(return_value=None)
    page.mouse = MagicMock()
    page.mouse.wheel = AsyncMock(return_value=None)
    page.mouse.move = AsyncMock(return_value=None)

    scrollable_div = MagicMock()
    inner_locator = MagicMock()
    inner_locator.all = AsyncMock(return_value=[])
    scrollable_div.locator = MagicMock(return_value=inner_locator)
    scrollable_div.hover = AsyncMock(return_value=None)
    page.locator = MagicMock(return_value=scrollable_div)

    return page


async def _collect(scanner: SidebarScraper, tile_id: str) -> list[Any]:
    return [
        item
        async for item in scanner.scrape(
            search_string="rubber-flooring-contractor",
            processed_place_ids=set(),
            force_refresh=False,
            ttl_days=30,
            tile_id=tile_id,
        )
    ]


@pytest.mark.asyncio
async def test_out_of_tile_recenter_short_circuits_without_scanning() -> None:
    # Google settled far outside the requested tile's bounds.
    page = _make_page("https://www.google.com/maps/search/rubber+flooring/@10.0,-70.0,10z")
    scanner = SidebarScraper(page)

    items = await _collect(scanner, TILE_ID)

    assert items == []
    # The scan loop's own div-locator must never be reached - proves this
    # returned fast instead of scrolling/scanning content it would discard.
    scrollable_div = page.locator.return_value
    scrollable_div.locator.assert_not_called()


@pytest.mark.asyncio
async def test_in_tile_center_still_enters_scan_loop() -> None:
    # Google settled inside the requested tile's bounds - normal path.
    page = _make_page("https://www.google.com/maps/search/rubber+flooring/@18.15,-66.05,15z")
    scanner = SidebarScraper(page)

    items = await _collect(scanner, TILE_ID)

    assert items == []  # empty feed, but via the real scan loop, not the fast path
    scrollable_div = page.locator.return_value
    scrollable_div.locator.assert_called_with("> div")
    assert scrollable_div.locator.call_count >= 1


@pytest.mark.asyncio
async def test_no_tile_id_skips_resize_check_entirely() -> None:
    # Non-grid (spiral) mode has no tile_id - resize check must not apply.
    page = _make_page("https://www.google.com/maps/search/rubber+flooring/@10.0,-70.0,10z")
    scanner = SidebarScraper(page)

    items = await _collect(scanner, tile_id=None)  # type: ignore[arg-type]

    assert items == []
    scrollable_div = page.locator.return_value
    scrollable_div.locator.assert_called_with("> div")


@pytest.mark.asyncio
async def test_zoom_drop_alone_short_circuits_even_with_center_in_bounds() -> None:
    """Center point staying inside the tile isn't enough on its own - a
    zoomed-out view can have an in-bounds center while the actual visible
    search area covers far more than the tile."""
    page = _make_page("https://www.google.com/maps/search/rubber+flooring/@18.15,-66.05,10z")
    scanner = SidebarScraper(page)

    items = await _collect(scanner, TILE_ID)

    assert items == []
    scrollable_div = page.locator.return_value
    scrollable_div.locator.assert_not_called()


class _DriftingPage:
    """Page double whose .url changes across successive reads (clamped to
    the last value once exhausted) - a static mock can't represent Google's
    viewport drifting mid-scan, which is the exact bug confirmed live
    2026-08-16: correctly in-bounds at the start, drifting only after the
    scan is already underway."""

    def __init__(self, urls: list[str]) -> None:
        self._urls = urls
        self._index = 0
        self.mouse = MagicMock()
        self.mouse.wheel = AsyncMock(return_value=None)
        self.mouse.move = AsyncMock(return_value=None)
        self.wait_for_selector = AsyncMock(return_value=None)
        self.wait_for_timeout = AsyncMock(return_value=None)

        scrollable_div = MagicMock()
        inner_locator = MagicMock()
        inner_locator.all = AsyncMock(return_value=[])
        scrollable_div.locator = MagicMock(return_value=inner_locator)
        scrollable_div.hover = AsyncMock(return_value=None)
        self.locator = MagicMock(return_value=scrollable_div)

    def is_closed(self) -> bool:
        return False

    @property
    def url(self) -> str:
        idx = min(self._index, len(self._urls) - 1)
        self._index += 1
        return self._urls[idx]


@pytest.mark.asyncio
async def test_drift_developing_mid_scan_stops_loop() -> None:
    """The bug an up-front-only check structurally cannot catch: URL is
    correctly in-bounds on the first check (so the loop proceeds, matching
    a real scan that starts fine), then drifts by a later check (simulating
    Google progressively zooming out as the scan scrolls). The loop must
    stop as soon as the drift is observed, not run to its normal stall
    detector or the idle-timeout ceiling."""
    page = _DriftingPage(
        [
            "https://www.google.com/maps/search/rubber+flooring/@18.15,-66.05,13z",  # in bounds
            "https://www.google.com/maps/search/rubber+flooring/@33.9498833,-118.7736081,11z",  # drifted
        ]
    )
    scanner = SidebarScraper(page)  # type: ignore[arg-type]

    items = await _collect(scanner, TILE_ID)

    assert items == []
    # Proves the loop actually entered (unlike the up-front short-circuit
    # cases above) before stopping on the second check.
    assert page._index >= 2
