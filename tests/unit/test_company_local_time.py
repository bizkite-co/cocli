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


def test_phone_area_code_resolves_timezone_when_nothing_else_does() -> None:
    """Austin Somers (higginbotham-austin-somers), 2026-10-06: a per-person
    company record with no address/city/state/zip at all, just a direct-dial
    817 (Fort Worth, TX) number - previously silently fell back to the
    operator's own machine timezone, mislabeled as "company local"."""
    place = resolve_company_place(phone_numbers=["+18173492327"])
    assert place.tz == ZoneInfo("America/Chicago")
    assert place.is_fallback is False


def test_phone_area_code_is_outranked_by_explicit_city_or_zip() -> None:
    """An 817 (Central) number shouldn't override an explicit NY zip -
    phone is a last-resort signal, not an authority over real address data."""
    place = resolve_company_place(zip_code="10001", phone_numbers=["+18173492327"])
    assert place.tz == ZoneInfo("America/New_York")


def test_phone_area_code_outranks_state_level_guess() -> None:
    """A precise area code should win over a generic state-level default
    when both are present and would disagree (state here is deliberately
    wrong/stale to prove phone takes priority)."""
    place = resolve_company_place(state="CA", phone_numbers=["+18173492327"])
    assert place.tz == ZoneInfo("America/Chicago")


def test_unparseable_phone_numbers_are_skipped_without_crashing() -> None:
    place = resolve_company_place(phone_numbers=["not-a-phone-number", ""])
    assert place.is_fallback is True


def test_no_location_signal_at_all_is_labeled_as_unknown_not_company_local() -> None:
    """Previously labeled "company local" even when nothing resolved and
    the clock was silently the operator's own machine time - now explicit
    about what's actually being shown."""
    place = resolve_company_place()
    assert place.is_fallback is True
    assert "unknown" in place.place_label()
    assert "your local time" in place.place_label()


def test_resolved_location_is_not_flagged_as_fallback() -> None:
    place = resolve_company_place(state="NY")
    assert place.is_fallback is False
    assert place.place_label() == "NY"