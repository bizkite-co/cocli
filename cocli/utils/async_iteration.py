"""Idle-timeout iteration over an async generator.

Distinguishes "still making progress, just slow" from "genuinely stuck" -
the two failure modes a single fixed asyncio.timeout() around a whole loop
can't tell apart. A generator that keeps yielding real items never trips
the idle clock, no matter how long the overall task runs; a generator that
stops producing anything gets caught fast instead of burning the full
absolute ceiling.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, TypeVar

T = TypeVar("T")


class IdleTimeoutError(TimeoutError):
    """Raised when no item was yielded within idle_timeout_s, even though
    the absolute deadline hasn't been reached."""


async def iterate_with_idle_timeout(
    source: AsyncIterator[T],
    *,
    idle_timeout_s: float,
    absolute_timeout_s: float,
) -> AsyncIterator[T]:
    """Wraps an async iterator so the deadline resets on every yielded item.

    Two independent limits, enforced together via a single rescheduled
    asyncio.timeout():
    - idle_timeout_s: max time to wait for the *next* item. Resets every
      time one arrives - a source that keeps producing real items can run
      indefinitely without tripping this.
    - absolute_timeout_s: hard ceiling regardless of progress - a backstop
      against a source that keeps yielding forever without ever finishing
      (e.g. a duplicate-heavy feed that never terminates cleanly).

    Raises IdleTimeoutError if idle_timeout_s elapses with no new item.
    Raises TimeoutError (bare) if absolute_timeout_s elapses overall.
    """
    loop = asyncio.get_running_loop()
    start = loop.time()
    absolute_deadline = start + absolute_timeout_s

    try:
        async with asyncio.timeout_at(min(start + idle_timeout_s, absolute_deadline)) as cm:
            while True:
                try:
                    item = await source.__anext__()
                except StopAsyncIteration:
                    return
                yield item
                now = loop.time()
                next_deadline = min(now + idle_timeout_s, absolute_deadline)
                cm.reschedule(next_deadline)
    except TimeoutError:
        # asyncio.timeout_at's __aexit__ converts its internal
        # CancelledError to TimeoutError on the way out of the `async
        # with` above - this except must wrap that block, not sit inside
        # it, or it never sees a TimeoutError to catch.
        if loop.time() >= absolute_deadline - 0.05:
            raise
        raise IdleTimeoutError(
            f"No item yielded within {idle_timeout_s}s (idle timeout)"
        ) from None
