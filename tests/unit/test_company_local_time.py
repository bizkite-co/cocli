from __future__ import annotations

from zoneinfo import ZoneInfo

from cocli.utils.company_local_time import format_company_local_now, resolve_company_tz


def test_resolve_company_tz_iana() -> None:
    tz = resolve_company_tz("America/Los_Angeles")
    assert tz == ZoneInfo("America/Los_Angeles")


def test_resolve_company_tz_abbrev() -> None:
    tz = resolve_company_tz("PDT")
    assert tz == ZoneInfo("America/Los_Angeles")


def test_resolve_company_tz_from_state() -> None:
    tz = resolve_company_tz(None, "NY")
    assert tz == ZoneInfo("America/New_York")


def test_format_company_local_now_includes_clock_and_zone() -> None:
    stamp = format_company_local_now("America/New_York")
    assert ":" in stamp
    assert "AM" in stamp or "PM" in stamp
    # ZoneInfo %Z is EDT/EST (or the IANA key as fallback).
    assert "EDT" in stamp or "EST" in stamp or "America/New_York" in stamp