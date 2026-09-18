from __future__ import annotations

from zoneinfo import ZoneInfo

from cocli.utils.company_local_time import (
    extract_us_location,
    format_company_local_now,
    resolve_company_place,
    resolve_company_tz,
)


def test_resolve_company_tz_iana() -> None:
    tz = resolve_company_tz("America/Los_Angeles")
    assert tz == ZoneInfo("America/Los_Angeles")


def test_resolve_company_tz_abbrev() -> None:
    tz = resolve_company_tz("PDT")
    assert tz == ZoneInfo("America/Los_Angeles")


def test_resolve_company_tz_from_state() -> None:
    tz = resolve_company_tz(None, "NY")
    assert tz == ZoneInfo("America/New_York")


def test_resolve_company_tz_from_full_state_name() -> None:
    place = resolve_company_place(state="Texas")
    assert place.tz == ZoneInfo("America/Chicago")
    assert place.state == "TX"


def test_dallas_address_text_is_central_time() -> None:
    """aquila-financial-tax-services: street only on the company record,
    'Dallas, TX 75240' in website copy — must not fall back to the
    operator's local PDT."""
    place = resolve_company_place(
        address_text="13355 Noel Rd\nLocated in North Dallas\nDallas, TX 75240"
    )
    assert place.tz == ZoneInfo("America/Chicago")
    assert place.state == "TX"
    assert place.zip_code == "75240"
    assert place.place_label() == "Dallas, TX"


def test_zip_75240_is_central() -> None:
    place = resolve_company_place(zip_code="75240")
    assert place.tz == ZoneInfo("America/Chicago")


def test_extract_us_location_from_city_state_zip() -> None:
    city, state, zip_code = extract_us_location("Dallas, TX 75240")
    assert city == "Dallas"
    assert state == "TX"
    assert zip_code == "75240"


def test_format_company_local_now_includes_clock_and_zone() -> None:
    stamp = format_company_local_now("America/New_York")
    assert ":" in stamp
    assert "AM" in stamp or "PM" in stamp
    # ZoneInfo %Z is EDT/EST (or the IANA key as fallback).
    assert "EDT" in stamp or "EST" in stamp or "America/New_York" in stamp