"""GoogleMapsListItem -> GoogleMapsProspect field-lineage integrity.

Registers the transform with the same checker used for the gm-list ->
gm-details pipeline (cocli/core/audit/field_lineage.py) so a future rename
or dropped field on either model fails a test instead of silently breaking
the WAL write this transform exists to enable.
"""

from typing import Any

from cocli.core.audit.field_lineage import FieldMap, assert_transform_field_integrity
from cocli.core.transformers.gm_list_item_to_prospect import (
    transform_gm_list_item_to_google_maps_prospect,
)
from cocli.models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

_PLACE_ID = "ChIJ" + "x" * 22

LIST_ITEM_TO_PROSPECT = FieldMap(
    name="gm_list_item_to_prospect -> GoogleMapsProspect",
    source_fields={
        "place_id", "company_slug", "name", "category", "phone", "domain",
        "reviews_count", "average_rating", "street_address", "gmb_url",
        "discovery_phrase", "discovery_tile_id", "html",
    },
    target_fields={
        "place_id", "slug", "name", "category", "phone", "domain",
        "reviews_count", "average_rating", "street_address", "gmb_url",
        "discovery_phrase", "discovery_tile_id",
    },
    map={
        "place_id": "place_id",
        "company_slug": "slug",
        "name": "name",
        "category": "category",
        "phone": "phone",
        "domain": "domain",
        "reviews_count": "reviews_count",
        "average_rating": "average_rating",
        "street_address": "street_address",
        "gmb_url": "gmb_url",
        "discovery_phrase": "discovery_phrase",
        "discovery_tile_id": "discovery_tile_id",
    },
    # gm-list's raw HTML has no destination field on the prospect model.
    source_unmapped={"html"},
)


_STRUCTURED_FIELDS = {"phone", "street_address"}


def _get_target_field(result: Any, field: str) -> Any:
    """phone/street_address are structured Pydantic types (PhoneNumber,
    CompanyAddress) needing str() to compare against a plain source string;
    everything else (ints, floats, plain strings) compares as-is."""
    value = getattr(result, field)
    if field in _STRUCTURED_FIELDS and value is not None:
        return str(value)
    return value


def test_list_item_to_prospect_field_integrity() -> None:
    def call_transform(values: dict[str, Any]) -> object:
        item = GoogleMapsListItem.model_validate(
            {
                "place_id": values["place_id"],
                "company_slug": values["company_slug"],
                "name": values["name"],
                "category": values["category"],
                "phone": values["phone"],
                "domain": values["domain"],
                "reviews_count": values["reviews_count"],
                "average_rating": values["average_rating"],
                "street_address": values["street_address"],
                "gmb_url": values["gmb_url"],
                "discovery_phrase": values["discovery_phrase"],
                "discovery_tile_id": values["discovery_tile_id"],
            }
        )
        return transform_gm_list_item_to_google_maps_prospect(item)

    source_values = {
        "place_id": _PLACE_ID,
        "company_slug": "test-flooring-co",
        "name": "Test Flooring Co",
        "category": "Flooring contractor",
        # OptionalPhone parses to a PhoneNumber(cc/ndc/sn/ext) struct on both
        # models. "15551234567" is a verified fixed point of that parser
        # (str(parse(x)) == x) - most human-entered formats (e.g. a hyphenated
        # "555-123-4567") don't round-trip byte-identically even though the
        # value itself is preserved correctly, so a fixed point avoids
        # asserting on that unrelated normalization quirk.
        "phone": "15551234567",
        "domain": "testflooring.com",
        "reviews_count": 42,
        "average_rating": 4.5,
        "street_address": "123 Main St",
        "gmb_url": "https://maps.google.com/x",
        "discovery_phrase": "flooring-contractor",
        "discovery_tile_id": "34.1_-118.4_flooring-contractor",
    }
    assert_transform_field_integrity(
        LIST_ITEM_TO_PROSPECT,
        source_values,
        call_transform,
        get_target_field=_get_target_field,
    )


def test_transform_produces_valid_prospect_with_minimal_fields() -> None:
    """No fields beyond the two required ones - proves defaults (created_at,
    version, etc.) don't need list-item data to construct a valid record."""
    item = GoogleMapsListItem.model_validate(
        {"place_id": _PLACE_ID, "company_slug": "minimal-co"}
    )
    prospect = transform_gm_list_item_to_google_maps_prospect(item)
    assert isinstance(prospect, GoogleMapsProspect)
    assert prospect.place_id == _PLACE_ID
    assert prospect.slug == "minimal-co"
