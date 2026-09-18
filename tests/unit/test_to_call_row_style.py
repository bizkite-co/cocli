"""_to_call_row_style() - color-codes to-call list rows by callback
due-status (overdue -> orange, due-soon -> yellow, else no special
color), per the to-call-list-sort-and-color-code-by-callback-due-status
ticket (Mark, 2026-09-17)."""

from __future__ import annotations

from datetime import datetime, timedelta, UTC

from cocli.tui.widgets.company_list import _to_call_row_style


def test_no_callback_at_means_no_special_style() -> None:
    assert _to_call_row_style(None) is None
    assert _to_call_row_style("") is None


def test_overdue_callback_is_orange() -> None:
    overdue = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    assert _to_call_row_style(overdue) == "bold orange1"


def test_due_soon_callback_is_yellow() -> None:
    soon = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    assert _to_call_row_style(soon) == "bold yellow"


def test_far_future_callback_has_no_special_style() -> None:
    far = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    assert _to_call_row_style(far) is None


def test_malformed_callback_at_is_treated_as_no_style() -> None:
    assert _to_call_row_style("not-a-date") is None


def test_naive_datetime_string_is_treated_as_utc() -> None:
    """callback_at strings from SearchResult (SQL-round-tripped) may lack
    a timezone suffix - must not crash comparing naive vs aware."""
    naive_overdue = (datetime.now(UTC) - timedelta(days=1)).replace(tzinfo=None).isoformat()
    assert _to_call_row_style(naive_overdue) == "bold orange1"
