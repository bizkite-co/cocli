"""Regression test for the home_url hardcoded-coordinate bug.

Confirmed via git archaeology 2026-08-16: commit e6e46331 (2026-03-05,
"achieving absolute high-fidelity for Google Maps") replaced a correctly
parameterized navigation URL with a fixed debug/ground-truth coordinate near
Los Angeles, active for 164 days. Every "human flow" search (the common
case) silently searched from that fixed point regardless of the requested
tile, until the per-item geographic bounds filter discarded whatever it
found - see task-agent ticket
regression-gm-list-stuck-at-60-for-months-broken-stealth-script-and-no-backoff-on-google-block-detection.

Parametrized across several geographically distinct locations specifically
so a reintroduced hardcoded constant can't accidentally satisfy the
assertion for more than one of them.
"""

import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from cocli.scrapers.google.gm_scraper.navigator import Navigator

_URL_LATLON_RE = re.compile(r"@(-?\d+\.?\d*),(-?\d+\.?\d*),")


def _make_page() -> MagicMock:
    page = MagicMock()
    page.goto = AsyncMock(return_value=None)

    locator_result = MagicMock()
    locator_result.first = MagicMock()
    locator_result.first.wait_for = AsyncMock(return_value=None)
    page.locator = MagicMock(return_value=locator_result)

    return page


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "lat,lon",
    [
        (40.7128, -74.0060),  # New York
        (25.7617, -80.1918),  # Miami
        (47.6062, -122.3321),  # Seattle
        (18.4655, -66.1057),  # Puerto Rico
    ],
)
async def test_goto_navigates_to_the_requested_location_not_a_fixed_one(
    lat: float, lon: float
) -> None:
    page = _make_page()
    navigator = Navigator(page)

    success = await navigator.goto(lat, lon, 8.0, 8.0, query="")

    assert success is True
    first_goto_url = page.goto.call_args_list[0].args[0]
    match = _URL_LATLON_RE.search(first_goto_url)
    assert match, f"No lat/lon found in the navigated URL: {first_goto_url}"
    assert float(match.group(1)) == pytest.approx(lat, abs=1e-4)
    assert float(match.group(2)) == pytest.approx(lon, abs=1e-4)


@pytest.mark.asyncio
async def test_two_different_calls_navigate_to_two_different_urls() -> None:
    """The most direct possible guard against a hardcoded constant: the
    same Navigator instance, called twice with different coordinates, must
    produce two different navigation URLs."""
    page = _make_page()
    navigator = Navigator(page)

    await navigator.goto(40.7128, -74.0060, 8.0, 8.0, query="")
    await navigator.goto(25.7617, -80.1918, 8.0, 8.0, query="")

    assert page.goto.call_count == 2
    first_url = page.goto.call_args_list[0].args[0]
    second_url = page.goto.call_args_list[1].args[0]
    assert first_url != second_url
