"""wait_until_page_painted holds screenshot until SPA shells settle.

Bounded waits; timeouts must not raise so the caller can still screenshot.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from cocli.utils.playwright_utils import wait_until_page_painted


@pytest.mark.asyncio
async def test_wait_until_page_painted_uses_bounded_networkidle() -> None:
    page = AsyncMock()

    await wait_until_page_painted(page, timeout_ms=8000)

    page.wait_for_load_state.assert_awaited_once_with("networkidle", timeout=4000)
    page.wait_for_function.assert_awaited_once()
    assert page.wait_for_function.await_args.kwargs["timeout"] == 8000
    page.evaluate.assert_awaited_once()


@pytest.mark.asyncio
async def test_wait_until_page_painted_caps_networkidle_to_overall_timeout() -> None:
    page = AsyncMock()

    await wait_until_page_painted(page, timeout_ms=2000)

    page.wait_for_load_state.assert_awaited_once_with("networkidle", timeout=2000)


@pytest.mark.asyncio
async def test_wait_until_page_painted_swallows_timeouts() -> None:
    page = AsyncMock()
    page.wait_for_load_state = AsyncMock(side_effect=RuntimeError("Timeout 4000ms exceeded"))
    page.wait_for_function = AsyncMock(side_effect=RuntimeError("Timeout 8000ms exceeded"))
    page.evaluate = AsyncMock(side_effect=RuntimeError("Execution context was destroyed"))

    await wait_until_page_painted(page, timeout_ms=8000)

    page.wait_for_load_state.assert_awaited()
    page.wait_for_function.assert_awaited()
    page.evaluate.assert_awaited()


@pytest.mark.asyncio
async def test_wait_until_page_painted_bounds_a_hung_evaluate() -> None:
    """Regression test for the enrichment worker's indefinite hang
    (2026-09-04): page.evaluate() has no `timeout` parameter of its own -
    unlike wait_for_load_state/wait_for_function above - so a page whose
    requestAnimationFrame never fires (real-world: headless Chromium under
    load) previously hung this function, and every enrichment task after
    it, forever. Outer asyncio.wait_for is a test-suite safety net, not the
    fix under test - if the internal bound regresses, this fails fast
    instead of hanging the suite."""
    page = AsyncMock()

    async def _never_resolves(*args: object, **kwargs: object) -> None:
        await asyncio.Event().wait()

    page.evaluate = AsyncMock(side_effect=_never_resolves)

    start = time.monotonic()
    await asyncio.wait_for(wait_until_page_painted(page, timeout_ms=8000), timeout=5.0)
    elapsed = time.monotonic() - start

    assert elapsed < 5.0
    page.evaluate.assert_awaited_once()
