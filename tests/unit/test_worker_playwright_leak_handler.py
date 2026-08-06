"""Tests for the orphaned-Playwright-Future exception handler workaround
documented on ticket
investigate-orphaned-playwright-future-targetclosederror-from-idle-timeout-cancellation
(see cocli/application/worker_service.py)."""

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

from cocli.application.worker_service import (
    _is_orphaned_playwright_future,
    _write_orphaned_playwright_future_record,
    install_playwright_leak_exception_handler,
)
from cocli.core.paths import paths


class TargetClosedError(Exception):
    """Stands in for playwright._impl._errors.TargetClosedError. __module__
    is overridden below to mimic the real module path, since the handler
    matches on type(exc).__module__.startswith("playwright"), not
    isinstance - deliberately, so it doesn't need to import Playwright's
    private module either."""


TargetClosedError.__module__ = "playwright._impl._errors"


class LocatorTimeoutError(Exception):
    """Stands in for playwright._impl._errors.TimeoutError (renamed here to
    avoid shadowing the builtin) - the second confirmed real-world shape:
    a locator visibility wait's own TimeoutError, orphaned the same way as
    the low-level protocol callback Future."""


LocatorTimeoutError.__module__ = "playwright._impl._errors"


def test_is_orphaned_playwright_future_matches_target_closed_error() -> None:
    context = {
        "message": "Future exception was never retrieved",
        "exception": TargetClosedError(
            "Target page, context or browser has been closed"
        ),
    }
    assert _is_orphaned_playwright_future(context) is True


def test_is_orphaned_playwright_future_matches_locator_timeout_error() -> None:
    """Live cluster audit confirmed this second shape: a Playwright
    TimeoutError from a locator visibility wait, orphaned the same way -
    the matcher must cover it too, not just TargetClosedError by name."""
    context = {
        "message": "Future exception was never retrieved",
        "exception": LocatorTimeoutError("Timeout 500ms exceeded."),
    }
    assert _is_orphaned_playwright_future(context) is True


def test_is_orphaned_playwright_future_rejects_non_playwright_exceptions() -> None:
    context = {
        "message": "Future exception was never retrieved",
        "exception": ValueError("something else"),
    }
    assert _is_orphaned_playwright_future(context) is False


def test_is_orphaned_playwright_future_rejects_our_own_idle_timeout_error() -> None:
    """Our own IdleTimeoutError (module cocli.utils.async_iteration) is
    caught and logged deliberately elsewhere ("Task Failed: ...") - it must
    keep flowing through the normal default handler, not get swallowed just
    because it's also a TimeoutError."""
    from cocli.utils.async_iteration import IdleTimeoutError

    context = {
        "message": "Future exception was never retrieved",
        "exception": IdleTimeoutError("No item yielded within 90s (idle timeout)"),
    }
    assert _is_orphaned_playwright_future(context) is False


def test_is_orphaned_playwright_future_rejects_non_retrieval_messages() -> None:
    """A TargetClosedError raised somewhere we *do* await it must not be
    swallowed just because of its type - only the specific "never
    retrieved" shape (an orphaned Future, not a live raised exception) is
    the known-benign case this handler exists for."""
    context = {
        "message": "Task exception was never retrieved",  # close but not exact
        "exception": TargetClosedError("..."),
    }
    # "never retrieved" substring still present in "Task exception was never
    # retrieved" - Tasks orphaning the same way is the same shape, so this
    # should still match.
    assert _is_orphaned_playwright_future(context) is True

    context_live_raise = {
        "message": "some other unrelated message",
        "exception": TargetClosedError("..."),
    }
    assert _is_orphaned_playwright_future(context_live_raise) is False


def test_install_playwright_leak_exception_handler_suppresses_known_shape() -> None:
    loop = asyncio.new_event_loop()
    try:
        install_playwright_leak_exception_handler(loop, "test-campaign")
        loop.default_exception_handler = MagicMock()  # type: ignore[method-assign]

        loop.call_exception_handler(
            {
                "message": "Future exception was never retrieved",
                "exception": TargetClosedError(
                    "Target page, context or browser has been closed"
                ),
            }
        )

        loop.default_exception_handler.assert_not_called()
    finally:
        loop.close()


def test_install_playwright_leak_exception_handler_passes_through_other_errors() -> None:
    """Everything that isn't the specific known-benign shape must still
    reach the loop's normal default handler unchanged - this is a targeted
    suppression, not a blanket exception-handler override."""
    loop = asyncio.new_event_loop()
    try:
        install_playwright_leak_exception_handler(loop, "test-campaign")
        loop.default_exception_handler = MagicMock()  # type: ignore[method-assign]

        context = {
            "message": "Future exception was never retrieved",
            "exception": ValueError("unrelated"),
        }
        loop.call_exception_handler(context)

        loop.default_exception_handler.assert_called_once_with(context)
    finally:
        loop.close()


def test_write_orphaned_playwright_future_record_appends_jsonl(tmp_path: Path) -> None:
    paths.root = tmp_path
    context = {
        "message": "Future exception was never retrieved",
        "exception": TargetClosedError(
            "Target page, context or browser has been closed"
        ),
    }

    _write_orphaned_playwright_future_record("test-campaign", context)
    _write_orphaned_playwright_future_record("test-campaign", context)

    log_path = (
        paths.campaign("test-campaign").path / "logs" / "playwright_leaked_futures.jsonl"
    )
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    record = json.loads(lines[0])
    assert record["exception_type"] == "TargetClosedError"
    assert record["exception_module"] == "playwright._impl._errors"
    assert "timestamp" in record


def test_write_orphaned_playwright_future_record_swallows_write_failures(
    tmp_path: Path,
) -> None:
    """Runs from inside an exception handler - a failure writing the
    tracking file (disk full, permissions) must not also break the default
    exception-handler fallback for genuinely unrelated errors."""
    paths.root = tmp_path / "does-not-exist" / "\x00invalid"
    context = {
        "message": "Future exception was never retrieved",
        "exception": TargetClosedError("..."),
    }

    _write_orphaned_playwright_future_record("test-campaign", context)  # must not raise
