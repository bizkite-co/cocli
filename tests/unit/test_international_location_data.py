"""International location data through the gm-details R path.

Fixture: University of Copenhagen detail scrape (unit of Copenhagen's Maps
page captured offline - no live Maps call). Asserts the witness URL's pin
coordinates survive to the prospect, the Danish address line splits into
street / postal code / locality / country without ever writing a postal code
into city, and the timezone derives offline to Europe/Copenhagen.

Regression guards: a US address still splits exactly as before, fill-empty
never overwrites a value already on the company, and the USV layout (column
name and order) is untouched.
"""

from typing import Any

import pytest

from cocli.core.audit.field_lineage import (
    FieldMap,
    Fallback,
    assert_transform_field_integrity,
)
from cocli.core.text_utils import parse_postal_address
from cocli.scrapers.google.google_maps_parsers.maps_coordinates import (
    GeoPoint,
    maps_coordinates,
)
from cocli.utils.timezone_geo import ONE_ZONE_COUNTRIES, timezone_at

# --- The fixture ---

COPENHAGEN_POINT = GeoPoint(latitude=55.679577, longitude=12.5420772)

COPENHAGEN_WITNESS_URL = (
    "https://www.google.com/maps/place/University+of+Copenhagen"
    "/@55.679577,12.5420772,17z/data=!3d55.679577!4d12.5420772"
)

COPENHAGEN_ADDRESS = "B\u00fclowsvej 17, 1870 Frederiksberg, Denmark"

COPENHAGEN_DETAILS: dict[str, Any] = {
    "Name": "University of Copenhagen",
    "Full_Address": COPENHAGEN_ADDRESS,
    "Website": "https://www.ku.dk/",
    "Phone": "+45 35 32 26 26",
    "First_category": "University",
}

# Minimal detail-page HTML: just the address button the parser looks for.
COPENHAGEN_HTML = (
    "<html><h1>University of Copenhagen</h1>"
    '<button data-item-id="address">B\u00fclowsvej 17, 1870 Frederiksberg, Denmark</button>'
    "</html>"
)


# --- maps_coordinates ---


def test_pin_coordinates_from_witness_url() -> None:
    assert maps_coordinates(COPENHAGEN_WITNESS_URL) == COPENHAGEN_POINT


def test_pin_beats_camera() -> None:
    # Camera (viewport) differs from pin (the place): the pin must win.
    url = (
        "https://www.google.com/maps/place/Alice,TX"
        "/@27.75,98.0,13z/data=!3d27.7713!4d-98.0600"
    )
    assert maps_coordinates(url) == GeoPoint(27.7713, -98.0600)


def test_camera_falls_back_when_no_pin() -> None:
    url = "https://maps.google.com/maps?q=Denmark&ll=@55.6761,12.5683,14z"
    assert maps_coordinates(url) == GeoPoint(55.6761, 12.5683)


def test_maps_coordinates_rejects_non_urls() -> None:
    assert maps_coordinates(None) is None
    assert maps_coordinates("") is None
    assert maps_coordinates("https://example.com/nothing") is None


def test_list_view_parser_uses_shared_coordinate_parser() -> None:
    from bs4 import BeautifulSoup

    from cocli.scrapers.google.google_maps_parsers.extract_gmb_url_coordinates_place_id import (
        extract_gmb_url_coordinates_place_id,
    )

    html = BeautifulSoup(
        f'<a class="hfpxzc" href="{COPENHAGEN_WITNESS_URL}">KU</a>', "html.parser"
    )
    raw = extract_gmb_url_coordinates_place_id(html)
    assert raw["Latitude"] == str(COPENHAGEN_POINT.latitude)
    assert raw["Longitude"] == str(COPENHAGEN_POINT.longitude)
    assert raw["Coordinates"] == f"{COPENHAGEN_POINT.latitude},{COPENHAGEN_POINT.longitude}"


# --- parse_postal_address ---


def test_danish_address_splits_without_postal_in_city() -> None:
    parsed = parse_postal_address(COPENHAGEN_ADDRESS)
    assert parsed == {
        "street_address": "B\u00fclowsvej 17",
        "city": "Frederiksberg",
        "state": None,
        "zip": "1870",
        "country": "DK",
    }


def test_us_address_unchanged() -> None:
    parsed = parse_postal_address("123 Main St, Austin, TX 78701")
    assert parsed == {
        "street_address": "123 Main St",
        "city": "Austin",
        "state": "TX",
        "zip": "78701",
        "country": None,
    }


def test_country_stays_empty_for_unknown_pieces() -> None:
    # UK form is out of scope for the first cut: leave components empty,
    # never guess, never write a postal fragment into city.
    parsed = parse_postal_address("73 Endell St, London SW1A 2AA, UK")
    assert parsed["country"] == "GB"
    assert parsed["city"] is None
    assert parsed["zip"] is None
    assert parsed["state"] is None
    assert parsed["street_address"] == "73 Endell St"


def test_alpha2_country_name_accepts_bare_code() -> None:
    parsed = parse_postal_address("B\u00fclowsvej 17, 1870 Frederiksberg, DK")
    assert parsed["country"] == "DK"
    assert parsed["city"] == "Frederiksberg"
    assert parsed["zip"] == "1870"


# --- maps address line no longer writes a postal code into city ---


def test_maps_place_model_never_copies_postal_into_city() -> None:
    from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

    prospect = GoogleMapsProspect(
        place_id="ChIJ-test-place-id-ku-000000000000",
        slug="university-of-copenhagen-di-ku",
        name="University of Copenhagen",
        full_address=COPENHAGEN_ADDRESS,
    )
    assert prospect.street_address == "B\u00fclowsvej 17"
    assert prospect.zip == "1870"
    assert prospect.city == "Frederiksberg"
    assert prospect.country == "DK"
    assert "1870" not in (prospect.city or "")


# --- end to end: detail parse -> raw -> prospect -> timezone ---


def test_parse_gmb_page_captures_coordinates_from_witness_url() -> None:
    from cocli.scrapers.google.google_maps_gmb_parser import parse_gmb_page

    details = parse_gmb_page(COPENHAGEN_HTML, witness_url=COPENHAGEN_WITNESS_URL)
    assert details["Full_Address"] == COPENHAGEN_ADDRESS
    assert details["Latitude"] == COPENHAGEN_POINT.latitude
    assert details["Longitude"] == COPENHAGEN_POINT.longitude
    assert details["Coordinates"] == f"{COPENHAGEN_POINT.latitude},{COPENHAGEN_POINT.longitude}"


def test_parse_gmb_page_without_witness_url_leaves_coordinates_empty() -> None:
    from cocli.scrapers.google.google_maps_gmb_parser import parse_gmb_page

    details = parse_gmb_page(COPENHAGEN_HTML)
    assert "Latitude" not in details


def test_copenhagen_detail_fixture_produces_full_location() -> None:
    from cocli.scrapers.google.google_maps_details import build_raw_result_from_details
    from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

    details_dict = parse_postal_address_fixture_details()
    analysis = {"is_value_resource": False, "fee_category": None, "rationale": None}

    raw = build_raw_result_from_details(
        details_dict,
        place_id="ChIJ-test-place-id-ku-000000000000",
        name=None,
        witness_url=COPENHAGEN_WITNESS_URL,
        processed_by="test",
        analysis=analysis,
    )
    assert raw is not None

    prospect = GoogleMapsProspect.from_raw(raw)
    assert prospect.street_address == "B\u00fclowsvej 17"
    assert prospect.zip == "1870"
    assert prospect.city == "Frederiksberg"
    assert prospect.country == "DK"
    assert prospect.latitude == pytest.approx(55.679577)
    assert prospect.longitude == pytest.approx(12.5420772)
    assert prospect.timezone == "Europe/Copenhagen"


def parse_postal_address_fixture_details() -> dict[str, Any]:
    """What parse_gmb_page(COPENHAGEN_HTML, witness_url=...) returns."""
    from cocli.scrapers.google.google_maps_gmb_parser import parse_gmb_page

    return parse_gmb_page(COPENHAGEN_HTML, witness_url=COPENHAGEN_WITNESS_URL)


# --- offline timezone helpers ---


def test_timezone_at_copenhagen() -> None:
    assert timezone_at(55.679577, 12.5420772) == "Europe/Copenhagen"


def test_timezone_at_us_point() -> None:
    assert timezone_at(30.2672, -97.7431) == "America/Chicago"


def test_timezone_at_none_for_missing_point() -> None:
    assert timezone_at(None, None) is None


def test_one_zone_map_excludes_multi_zone_countries() -> None:
    assert ONE_ZONE_COUNTRIES["DK"] == "Europe/Copenhagen"
    assert "US" not in ONE_ZONE_COUNTRIES
    assert "CA" not in ONE_ZONE_COUNTRIES
    assert "AU" not in ONE_ZONE_COUNTRIES


# --- resolve_company_place ---


def test_resolve_company_place_from_point() -> None:
    from cocli.utils.company_local_time import resolve_company_place

    place = resolve_company_place(latitude=55.679577, longitude=12.5420772)
    assert str(place.tz) == "Europe/Copenhagen"
    assert place.is_fallback is False


def test_resolve_company_place_still_resolves_zip_only_us_record() -> None:
    from cocli.utils.company_local_time import resolve_company_place

    place = resolve_company_place(zip_code="78701")
    assert not place.is_fallback
    assert str(place.tz) == "America/Chicago"


def test_resolve_company_place_one_zone_country_fallback() -> None:
    from cocli.utils.company_local_time import resolve_company_place

    place = resolve_company_place(country="DK")
    assert str(place.tz) == "Europe/Copenhagen"


def test_resolve_company_place_does_not_default_us_country() -> None:
    from cocli.utils.company_local_time import resolve_company_place

    place = resolve_company_place(country="US")
    assert place.is_fallback is True


def test_resolve_company_place_explicit_timezone_wins() -> None:
    from cocli.utils.company_local_time import resolve_company_place

    place = resolve_company_place(timezone_name="Europe/Copenhagen", zip_code="78701")
    assert str(place.tz) == "Europe/Copenhagen"


# --- fill-empty onto the company ---


@pytest.fixture
def sandboxed_companies_dir(tmp_path: Any):
    from unittest.mock import patch

    from cocli.core.paths import paths

    with patch.object(paths, "root", tmp_path):
        companies_dir = paths.companies.path
        companies_dir.mkdir(parents=True, exist_ok=True)
        yield companies_dir


def _ku_prospect(slug: str) -> Any:
    from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

    return GoogleMapsProspect(
        place_id="ChIJ-test-place-id-ku-000000000000",
        slug=slug,
        name="University of Copenhagen",
        full_address=COPENHAGEN_ADDRESS,
        latitude=55.679577,
        longitude=12.5420772,
        country="DK",
        timezone="Europe/Copenhagen",
    )


def test_apply_prospect_fills_empty_location_without_overwriting(
    sandboxed_companies_dir: Any,
) -> None:
    from cocli.models.companies.company import Company
    from cocli.core.importing import apply_prospect_to_company_if_empty
    from cocli.models.company_name import CompanyName

    # Company record written by hand: city Copenhagen, country DK, timezone set.
    company = Company(
        name=CompanyName("University of Copenhagen"),
        slug="university-of-copenhagen-di-ku",
        city="Copenhagen",
        country="DK",
        timezone="Europe/Copenhagen",
    )
    company.save(rebuild_cache=False)

    prospect = _ku_prospect("university-of-copenhagen-di-ku")
    assert apply_prospect_to_company_if_empty(prospect) is True

    loaded = Company.get("university-of-copenhagen-di-ku")
    assert loaded is not None
    # Missing coordinates filled; nothing else clobbered.
    assert loaded.latitude == pytest.approx(55.679577)
    assert loaded.longitude == pytest.approx(12.5420772)
    assert loaded.timezone == "Europe/Copenhagen"
    assert loaded.city == "Copenhagen"
    assert loaded.country == "DK"


def test_apply_prospect_does_not_overwrite_set_timezone(sandboxed_companies_dir: Any) -> None:
    from cocli.models.companies.company import Company
    from cocli.core.importing import apply_prospect_to_company_if_empty
    from cocli.models.company_name import CompanyName

    company = Company(
        name=CompanyName("Holding Co"),
        slug="holding-co",
        timezone="Europe/Copenhagen",
    )
    company.save(rebuild_cache=False)

    prospect = _ku_prospect("holding-co")
    apply_prospect_to_company_if_empty(prospect)
    loaded = Company.get("holding-co")
    assert loaded.timezone == "Europe/Copenhagen"


def test_import_prospect_copies_location_fields(sandboxed_companies_dir: Any) -> None:
    from cocli.core.importing import import_prospect
    from cocli.models.companies.company import Company

    prospect = _ku_prospect("university-of-copenhagen-di-ku")
    prospect.domain = "ku.dk"
    created = import_prospect(prospect, campaign="turboship")
    assert created is not None

    loaded = Company.get("university-of-copenhagen-di-ku")
    assert loaded.country == "DK"
    assert loaded.timezone == "Europe/Copenhagen"
    assert loaded.latitude == pytest.approx(55.679577)
    assert loaded.longitude == pytest.approx(12.5420772)

    # Fill semantics on the update path: a later scrape with empty data
    # must not null anything out.
    prospect.domain = None
    prospect.latitude = None
    prospect.country = None
    import_prospect(prospect, campaign="turboship")
    reloaded = Company.get("university-of-copenhagen-di-ku")
    assert reloaded.country == "DK"
    assert reloaded.latitude == pytest.approx(55.679577)


# --- field-lineage edge: details_dict -> GoogleMapsRawResult ---


DETAILS_TO_RAW = FieldMap(
    name="parse_gmb_page(detail page + witness url) -> GoogleMapsRawResult",
    source_fields={
        "Name", "Full_Address", "Website", "Phone",
        "Street_Address", "City", "Zip", "State", "Country", "Timezone",
        "Latitude", "Longitude", "Coordinates",
    },
    target_fields={
        "Name", "Full_Address", "Street_Address", "City", "Zip",
        "State", "Country", "Timezone", "Latitude", "Longitude", "Coordinates",
    },
    map={
        "Name": "Name",
        "Full_Address": "Full_Address",
        "Website": "Website",  # raw field is Phone_1 for Phone; Website matches
        "Phone": "Phone_1",
        "Latitude": "Latitude",
        "Longitude": "Longitude",
        "Coordinates": "Coordinates",
    },
    merge={
        # Page sometimes carries the components explicitly; parse_postal_address
        # (detail page's own Full_Address) is the same-scrape fallback.
        "Street_Address": Fallback(primary="Street_Address", fallback_field="_addr_street"),
        "City": Fallback(primary="City", fallback_field="_addr_city"),
        "Zip": Fallback(primary="Zip", fallback_field="_addr_zip"),
        "State": Fallback(primary="State", fallback_field="_addr_state"),
        "Country": Fallback(primary="Country", fallback_field="_addr_country"),
        # Timezone: only derived offline from this scrape's own point when
        # the page gave none (fill-empty, never overwrite).
        "Timezone": Fallback(primary="Timezone", fallback_field="_derived_timezone"),
    },
    source_unmapped=set(),
    target_unmapped={
        "Second_category", "Reviews_count", "Average_rating", "Reviews",
        "Thumbnail_URL", "Keyword", "Municipality", "Place_ID",
    },
)


def test_details_to_raw_field_lineage() -> None:
    from cocli.scrapers.google.google_maps_details import build_raw_result_from_details

    analysis: dict[str, Any] = {
        "is_value_resource": False, "fee_category": None, "rationale": None,
    }

    def call_transform(values: dict[str, Any]) -> Any:
        addr = parse_postal_address(values["Full_Address"]) if values["Full_Address"] else {}
        lat, lon = values.get("Latitude"), values.get("Longitude")
        derived_tz = timezone_at(lat, lon) if lat and lon else None
        values.setdefault("_addr_street", addr.get("street_address"))
        values.setdefault("_addr_city", addr.get("city"))
        values.setdefault("_addr_zip", addr.get("zip"))
        values.setdefault("_addr_state", addr.get("state"))
        values.setdefault("_addr_country", addr.get("country"))
        values.setdefault("_derived_timezone", derived_tz)
        return build_raw_result_from_details(
            values,
            place_id="ChIJ-test-place-id-ku-000000000000",
            name=None,
            witness_url=COPENHAGEN_WITNESS_URL,
            processed_by="test",
            analysis=analysis,
        )

    # The production detail dict: no explicit components, no timezone.
    source_values: dict[str, Any] = {
        "Name": "University of Copenhagen",
        "Full_Address": COPENHAGEN_ADDRESS,
        "Website": "https://www.ku.dk/",
        "Phone": "+45 35 32 26 26",
        "Latitude": 55.679577,
        "Longitude": 12.5420772,
        "Coordinates": "55.679577,12.5420772",
    }
    assert_transform_field_integrity(DETAILS_TO_RAW, source_values, call_transform)


# --- USV layout unchanged ---


def test_usv_column_names_are_unchanged() -> None:
    from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

    fields = list(GoogleMapsProspect.model_fields.keys())
    assert "zip" in fields
    assert "zip_code" not in fields
    assert "postal_code" not in fields
    # Column order must stay untouched - stored rows are positional.
    assert fields.index("zip") < fields.index("timezone")
