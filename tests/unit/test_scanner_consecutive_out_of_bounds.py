"""Guards SidebarScraper.scrape()'s consecutive-out-of-tile early stop
(scanner.py).

Google's sidebar increasingly intersperses results from outside the target
tile deeper into the scroll - a separate, finer-grained signal from the
full viewport resize/zoom-out covered in test_scanner_viewport_resize.py.
Before this fix, each out-of-bounds item was discarded one at a time with
no memory of how many in a row had been rejected, so a scan could burn
time hovering/hydrating/parsing dozens of items it was always going to
discard, well before the coarser URL-based viewport-drift check ever
tripped. This test proves the scan now stops after a short run of
consecutive misses instead of working through an entire batch of results
we'd never use.
"""

from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cocli.scrapers.google.gm_scraper.scanner import (
    _MAX_CONSECUTIVE_OUT_OF_BOUNDS,
    SidebarScraper,
)

TILE_ID = "18.1_-66.1"  # bounds: lat [18.1, 18.2), lon [-66.1, -66.0)
IN_BOUNDS = {"Latitude": "18.15", "Longitude": "-66.05"}
OUT_OF_BOUNDS = {"Latitude": "10.0", "Longitude": "-70.0"}


def _fake_place_id(i: int) -> str:
    # Real Google place IDs are ~27 chars; GoogleMapsListItem enforces
    # min_length=26/max_length=29, so a short "PLACE_0"-style stub fails
    # model validation. Pad to exactly 26 chars.
    return f"ChIJfakePlaceID{i:011d}"


def _fake_parsed(i: int, coords: Dict[str, str]) -> Dict[str, Any]:
    return {"Place_ID": _fake_place_id(i), "Name": f"Business {i}", **coords}


def _make_page_with_divs(n_divs: int) -> MagicMock:
    page = MagicMock()
    page.is_closed.return_value = False
    # In-bounds, on the tile - the separate URL-drift check must not be
    # what stops this scan; only the per-item counter should.
    page.url = "https://www.google.com/maps/search/rubber+flooring/@18.15,-66.05,13z"
    page.wait_for_selector = AsyncMock(return_value=None)
    page.wait_for_timeout = AsyncMock(return_value=None)
    page.mouse = MagicMock()
    page.mouse.wheel = AsyncMock(return_value=None)
    page.mouse.move = AsyncMock(return_value=None)

    divs = [MagicMock() for _ in range(n_divs)]
    inner_locator = MagicMock()
    inner_locator.all = AsyncMock(return_value=divs)

    scrollable_div = MagicMock()
    scrollable_div.locator = MagicMock(return_value=inner_locator)
    scrollable_div.hover = AsyncMock(return_value=None)
    page.locator = MagicMock(return_value=scrollable_div)

    return page


@pytest.mark.asyncio
async def test_stops_after_consecutive_out_of_bounds_run_without_scanning_the_rest() -> None:
    # 2 real in-bounds items, then a run of out-of-bounds ones well past
    # the threshold - the tail must never be reached.
    n_in_bounds_lead = 2
    n_out_of_bounds_batch = _MAX_CONSECUTIVE_OUT_OF_BOUNDS + 10
    total_divs = n_in_bounds_lead + n_out_of_bounds_batch

    page = _make_page_with_divs(total_divs)
    scanner = SidebarScraper(page)
    scanner.capture_listing_html = AsyncMock(return_value="<div>fake</div>")  # type: ignore[method-assign]
    scanner.wait_for_hydration = AsyncMock(return_value=True)  # type: ignore[method-assign]

    parsed_sequence = [
        _fake_parsed(i, IN_BOUNDS if i < n_in_bounds_lead else OUT_OF_BOUNDS)
        for i in range(total_divs)
    ]

    with patch(
        "cocli.scrapers.google.google_maps_parser.parse_business_listing_html",
        side_effect=parsed_sequence,
    ) as mock_parse:
        items = [
            item
            async for item in scanner.scrape(
                search_string="rubber-flooring-contractor",
                processed_place_ids=set(),
                force_refresh=False,
                ttl_days=30,
                tile_id=TILE_ID,
            )
        ]

    # Only the 2 real in-bounds items were ever yielded.
    assert len(items) == n_in_bounds_lead
    assert {item.place_id for item in items} == {
        _fake_place_id(0),
        _fake_place_id(1),
    }

    # Parsing stopped right after the Nth consecutive out-of-bounds miss -
    # proves the scan didn't work through the rest of the (much longer) batch.
    assert mock_parse.call_count == n_in_bounds_lead + _MAX_CONSECUTIVE_OUT_OF_BOUNDS


@pytest.mark.asyncio
async def test_an_in_bounds_item_resets_the_streak() -> None:
    """A near-miss run shorter than the threshold, interrupted by a real
    in-bounds item, must not trip the stop - only a genuinely consecutive
    run counts."""
    near_miss_run = _MAX_CONSECUTIVE_OUT_OF_BOUNDS - 1
    # out-of-bounds x (threshold-1), then in-bounds (resets), then done.
    total_divs = near_miss_run + 1
    page = _make_page_with_divs(total_divs)
    scanner = SidebarScraper(page)
    scanner.capture_listing_html = AsyncMock(return_value="<div>fake</div>")  # type: ignore[method-assign]
    scanner.wait_for_hydration = AsyncMock(return_value=True)  # type: ignore[method-assign]

    parsed_sequence = [_fake_parsed(i, OUT_OF_BOUNDS) for i in range(near_miss_run)]
    parsed_sequence.append(_fake_parsed(near_miss_run, IN_BOUNDS))

    with patch(
        "cocli.scrapers.google.google_maps_parser.parse_business_listing_html",
        side_effect=parsed_sequence,
    ) as mock_parse:
        items = [
            item
            async for item in scanner.scrape(
                search_string="rubber-flooring-contractor",
                processed_place_ids=set(),
                force_refresh=False,
                ttl_days=30,
                tile_id=TILE_ID,
            )
        ]

    assert len(items) == 1
    assert items[0].place_id == _fake_place_id(near_miss_run)
    # All items were parsed - the near-miss run alone wasn't enough to stop.
    assert mock_parse.call_count == total_divs
