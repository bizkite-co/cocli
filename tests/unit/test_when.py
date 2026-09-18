from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cocli.utils.when import parse_follow_up_when


def test_parse_follow_up_when_iso_date() -> None:
    parsed = parse_follow_up_when("2026-09-30")
    assert parsed == datetime(2026, 9, 30, tzinfo=UTC)


def test_parse_follow_up_when_monday_is_a_future_monday() -> None:
    parsed = parse_follow_up_when("monday")
    now = datetime.now(UTC)
    assert parsed.weekday() == 0
    assert parsed > now - timedelta(seconds=5)


def test_parse_follow_up_when_next_week_is_in_the_future() -> None:
    parsed = parse_follow_up_when("next week")
    now = datetime.now(UTC)
    assert parsed > now
    assert parsed <= now + timedelta(days=14)


def test_parse_follow_up_when_rejects_empty() -> None:
    with pytest.raises(ValueError):
        parse_follow_up_when("   ")