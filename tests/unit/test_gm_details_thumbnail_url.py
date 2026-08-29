"""build_raw_result_from_details() must pass Thumbnail_URL through.

google_maps_gmb_parser.py already extracts a thumbnail URL from the
detail page's og:image meta tag into details_dict["Thumbnail_URL"], but
build_raw_result_from_details() never read it back out when constructing
GoogleMapsRawResult - the value was parsed successfully and silently
dropped one function away from being saved. GoogleMapsProspect's own
transform (google_maps_prospect.py) already reads raw.Thumbnail_URL, so
this was the only missing link in the chain.
"""

from __future__ import annotations

from cocli.scrapers.google.google_maps_details import build_raw_result_from_details

_PLACE_ID = "ChIJ" + "x" * 22


def _analysis() -> dict:
    return {"is_value_resource": True, "fee_category": None, "rationale": ""}


def test_thumbnail_url_passed_through_to_raw_result() -> None:
    details_dict = {
        "Name": "Test Flooring Co",
        "Thumbnail_URL": "https://lh3.googleusercontent.com/p/fake-thumbnail",
    }

    result = build_raw_result_from_details(
        details_dict,
        place_id=_PLACE_ID,
        name=None,
        witness_url="https://maps.google.com/?cid=123",
        processed_by="test-worker",
        analysis=_analysis(),
    )

    assert result is not None
    assert result.Thumbnail_URL == "https://lh3.googleusercontent.com/p/fake-thumbnail"


def test_missing_thumbnail_url_is_none_not_an_error() -> None:
    details_dict = {"Name": "Test Flooring Co"}

    result = build_raw_result_from_details(
        details_dict,
        place_id=_PLACE_ID,
        name=None,
        witness_url="https://maps.google.com/?cid=123",
        processed_by="test-worker",
        analysis=_analysis(),
    )

    assert result is not None
    assert result.Thumbnail_URL is None
