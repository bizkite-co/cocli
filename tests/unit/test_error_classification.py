"""classify_exception(): distinguishes site-attributable failures (never our
bug) from failures in our own code. See task-agent ticket
structured-error-classification-for-enrichmentscraping-failures."""

from pydantic import BaseModel, Field, ValidationError

from cocli.core.error_classification import ErrorCategory, classify_exception
from cocli.core.exceptions import EnrichmentError, NavigationError


class _Strict(BaseModel):
    name: str = Field(max_length=3)


def _make_validation_error() -> ValidationError:
    try:
        _Strict(name="way too long")
    except ValidationError as e:
        return e
    raise AssertionError("expected a ValidationError")


def test_navigation_error_is_navigation_failed():
    assert classify_exception(NavigationError("dns fail")) == ErrorCategory.NAVIGATION_FAILED


def test_timeout_error_is_timeout():
    assert classify_exception(TimeoutError("slow")) == ErrorCategory.TIMEOUT


def test_pydantic_validation_error_is_validation_failed():
    assert classify_exception(_make_validation_error()) == ErrorCategory.VALIDATION_FAILED


def test_unrelated_exception_is_scraper_bug():
    assert classify_exception(AttributeError("boom")) == ErrorCategory.SCRAPER_BUG
    assert classify_exception(EnrichmentError("generic enrichment failure")) == ErrorCategory.SCRAPER_BUG


def test_playwright_style_timeout_by_class_name_is_timeout():
    class TimeoutError_(Exception):  # mimics playwright's own TimeoutError, not builtin
        pass

    assert classify_exception(TimeoutError_("Timeout 30000ms exceeded")) == ErrorCategory.TIMEOUT
