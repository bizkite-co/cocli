"""Guards SidebarScraper.scrape()'s periodic (not just reactive) block check.

The 3 pre-existing call sites for check_and_alert_google_maps_block()
(navigator.py x2, gm_details_scraper.py) only fire on an exception path -
a "soft" block where the page loads fine but shows a CAPTCHA/rate-limit
page instead of real results wouldn't necessarily raise anything, so a
long scan could sit on a block page indefinitely. This proves the scan
loop itself now checks periodically and stops early on detection.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cocli.scrapers.google.gm_scraper.scanner import SidebarScraper


def _make_page_with_divs(n_divs: int) -> MagicMock:
    page = MagicMock()
    page.is_closed.return_value = False
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
async def test_scan_stops_early_when_block_detected_mid_scan() -> None:
    page = _make_page_with_divs(50)
    scanner = SidebarScraper(page)
    scanner.capture_listing_html = AsyncMock(return_value="<div>fake</div>")  # type: ignore[method-assign]
    scanner.wait_for_hydration = AsyncMock(return_value=True)  # type: ignore[method-assign]

    with patch(
        "cocli.utils.alert_utils.check_and_alert_google_maps_block",
        new=AsyncMock(return_value=True),
    ) as mock_block_check:
        items = [
            item
            async for item in scanner.scrape(
                search_string="rubber-flooring-contractor",
                processed_place_ids=set(),
                force_refresh=False,
                ttl_days=30,
                tile_id=None,
            )
        ]

    assert items == []
    mock_block_check.assert_awaited()


@pytest.mark.asyncio
async def test_scan_continues_normally_when_no_block_detected() -> None:
    page = _make_page_with_divs(0)
    scanner = SidebarScraper(page)

    with patch(
        "cocli.utils.alert_utils.check_and_alert_google_maps_block",
        new=AsyncMock(return_value=False),
    ) as mock_block_check:
        items = [
            item
            async for item in scanner.scrape(
                search_string="rubber-flooring-contractor",
                processed_place_ids=set(),
                force_refresh=False,
                ttl_days=30,
                tile_id=None,
            )
        ]

    assert items == []
    mock_block_check.assert_awaited()
