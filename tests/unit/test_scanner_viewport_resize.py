"""Guards SidebarScraper.scrape()'s viewport-resize fast-path (scanner.py).

Google auto-resizes/recenters the map for sparse tiles (e.g. over open ocean or
a large desert) and returns results from outside the requested tile instead.
The per-item tile-bounds filter already discards those one-by-one, but each
one still looks like "new" DOM content to the stall-detector, so the scan
loop used to run the full 90s idle-timeout instead of failing fast. This test
guards the up-front check that detects the resize from the settled map URL
and returns immediately, plus a regression guard that a normal in-bounds
session still proceeds into the scan loop unaffected.
"""

from typing import Any, List
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


async def _collect(scanner: SidebarScraper, tile_id: str) -> List[Any]:
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
