"""Tests for the orphaned-Playwright-callback exception handler workaround
documented on ticket
investigate-orphaned-playwright-future-targetclosederror-from-idle-timeout-cancellation
(see cocli/application/worker_service.py)."""

import asyncio
from unittest.mock import MagicMock

from cocli.application.worker_service import (
    _is_orphaned_playwright_target_closed,
    install_playwright_leak_exception_handler,
)


class TargetClosedError(Exception):
    """Stands in for playwright._impl._errors.TargetClosedError without
    depending on Playwright's private module - the handler matches on
    type(exc).__name__, not isinstance, precisely so it doesn't need to
    import that private module either. Must be named exactly
    "TargetClosedError" to exercise that name-based match."""


def test_is_orphaned_playwright_target_closed_matches_the_known_shape() -> None:
    context = {
        "message": "Future exception was never retrieved",
        "exception": TargetClosedError(
            "Target page, context or browser has been closed"
        ),
    }
    assert _is_orphaned_playwright_target_closed(context) is True


def test_is_orphaned_playwright_target_closed_rejects_other_exception_types() -> None:
    context = {
        "message": "Future exception was never retrieved",
        "exception": ValueError("something else"),
    }
    assert _is_orphaned_playwright_target_closed(context) is False


def test_is_orphaned_playwright_target_closed_rejects_non_retrieval_messages() -> None:
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
    assert _is_orphaned_playwright_target_closed(context) is True

    context_live_raise = {
        "message": "some other unrelated message",
        "exception": TargetClosedError("..."),
    }
    assert _is_orphaned_playwright_target_closed(context_live_raise) is False


def test_install_playwright_leak_exception_handler_suppresses_known_shape() -> None:
    loop = asyncio.new_event_loop()
    try:
        install_playwright_leak_exception_handler(loop)
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
        install_playwright_leak_exception_handler(loop)
        loop.default_exception_handler = MagicMock()  # type: ignore[method-assign]

        context = {
            "message": "Future exception was never retrieved",
            "exception": ValueError("unrelated"),
        }
        loop.call_exception_handler(context)

        loop.default_exception_handler.assert_called_once_with(context)
    finally:
        loop.close()
