"""iterate_with_idle_timeout: proves the fix for the real bug this session
found live - a gm-list scrape task that stopped yielding new items but sat
for the full 900s absolute timeout before failing, because a single fixed
asyncio.timeout() around the whole loop can't tell "stuck" from "slow but
progressing" apart. These tests use small, scaled-down timeouts so they run
in well under a second - no Playwright/browser dependency at all.
"""

import asyncio
from typing import AsyncIterator

import pytest

from cocli.utils.async_iteration import IdleTimeoutError, iterate_with_idle_timeout


async def _steady_source(n: int, gap_s: float) -> AsyncIterator[int]:
    for i in range(n):
        await asyncio.sleep(gap_s)
        yield i


async def _stalls_after(n: int, gap_s: float, stall_s: float) -> AsyncIterator[int]:
    for i in range(n):
        await asyncio.sleep(gap_s)
        yield i
    await asyncio.sleep(stall_s)
    yield 999  # never reached if the idle timeout fires first


@pytest.mark.asyncio
async def test_steady_source_completes_without_tripping_idle_timeout() -> None:
    """Total run time (10 * 0.02s = 0.2s) exceeds the idle timeout (0.05s)
    many times over, but no single gap does - must not raise."""
    results = [
        item
        async for item in iterate_with_idle_timeout(
            _steady_source(10, 0.02), idle_timeout_s=0.05, absolute_timeout_s=5.0
        )
    ]
    assert results == list(range(10))


@pytest.mark.asyncio
async def test_stalled_source_raises_idle_timeout_fast_not_at_absolute_ceiling() -> None:
    """A source that stops producing must fail at the idle timeout, not
    burn the (much larger) absolute ceiling - this is the exact bug: a
    stuck gm-list task waiting the full 900s instead of failing in ~90s."""
    start = asyncio.get_event_loop().time()
    with pytest.raises(IdleTimeoutError):
        async for _ in iterate_with_idle_timeout(
            _stalls_after(3, 0.01, stall_s=10.0),
            idle_timeout_s=0.05,
            absolute_timeout_s=5.0,
        ):
            pass
    elapsed = asyncio.get_event_loop().time() - start
    assert elapsed < 1.0, (
        f"idle timeout should fire in ~0.05s after the last item, not wait "
        f"anywhere near the 5.0s absolute ceiling (took {elapsed:.2f}s)"
    )


@pytest.mark.asyncio
async def test_absolute_timeout_is_a_backstop_even_if_never_idle() -> None:
    """A source that never stalls (always yields well within idle_timeout)
    but runs forever must still be bounded by the absolute ceiling."""
    with pytest.raises(TimeoutError) as exc_info:
        async for _ in iterate_with_idle_timeout(
            _steady_source(10_000, 0.01),
            idle_timeout_s=1.0,
            absolute_timeout_s=0.1,
        ):
            pass
    assert not isinstance(exc_info.value, IdleTimeoutError), (
        "must be the bare absolute-ceiling TimeoutError, not IdleTimeoutError - "
        "the source never actually stalled"
    )
