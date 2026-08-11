"""Shared error classification for scraping/enrichment failures.

Distinguishes failures that are never our bug (a site is down, blocked, or
returns garbage) from failures in our own code (an exception our parsing
logic didn't expect, or a Pydantic schema that's too strict for real-world
data). See task-agent ticket
structured-error-classification-for-enrichmentscraping-failures.
"""

from enum import Enum

from pydantic import ValidationError

from .exceptions import NavigationError


class ErrorCategory(str, Enum):
    NAVIGATION_FAILED = "navigation_failed"  # site unreachable/blocked/4xx/5xx - never our bug
    VALIDATION_FAILED = "validation_failed"  # scraped data didn't fit our schema
    TIMEOUT = "timeout"
    SCRAPER_BUG = "scraper_bug"  # unexpected exception after a successful page load


def classify_exception(exc: BaseException) -> ErrorCategory:
    """Best-effort classification of a caught exception for logging/reporting.

    Order matters: NavigationError may wrap a ValidationError-shaped message
    string but is checked first since navigation failures are identifiable
    before any parsing ever happens.
    """
    if isinstance(exc, NavigationError):
        return ErrorCategory.NAVIGATION_FAILED
    if isinstance(exc, TimeoutError):
        return ErrorCategory.TIMEOUT
    if isinstance(exc, ValidationError):
        return ErrorCategory.VALIDATION_FAILED
    if "timeout" in type(exc).__name__.lower():
        return ErrorCategory.TIMEOUT
    return ErrorCategory.SCRAPER_BUG
