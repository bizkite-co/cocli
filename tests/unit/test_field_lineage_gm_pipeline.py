"""Field-lineage integrity for the gm-list -> gm-details pipeline.

Two edges registered:
  1. GoogleMapsListItem.to_task -> GmItemTask: already correct in production
     code - proves the checker recognizes a good transform, not just flags
     everything.
  2. build_raw_result_from_details' category merge -> GoogleMapsRawResult.
     First_category: the documented "fallback when the detail page yields
     no First_category" (GmItemTask.category's own docstring), fixed by
     task-agent ticket recover-dropped-fields. This test used to carry an
     xfail(strict=True) marker proving the checker caught the bug before
     the fix landed - removed now that it passes for real.
"""

from typing import Any

from cocli.core.audit.field_lineage import (
    Fallback,
    FieldMap,
    assert_transform_field_integrity,
)
from cocli.models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem
from cocli.scrapers.google.google_maps_details import build_raw_result_from_details

_PLACE_ID = "ChIJ" + "x" * 22

LIST_ITEM_TO_TASK = FieldMap(
    name="google_maps_list_item.to_task -> GmItemTask",
    source_fields={
        "place_id", "company_slug", "name", "category", "phone", "domain",
        "reviews_count", "average_rating", "street_address", "gmb_url",
        "discovery_phrase", "discovery_tile_id", "html",
    },
    target_fields={
        "place_id", "campaign_name", "name", "company_slug", "force_refresh",
        "gmb_url", "category", "discovery_phrase", "discovery_tile_id",
        "ack_token", "attempts",
    },
    map={
        "place_id": "place_id",
        "company_slug": "company_slug",
        "name": "name",
        "category": "category",
        "gmb_url": "gmb_url",
        "discovery_phrase": "discovery_phrase",
        "discovery_tile_id": "discovery_tile_id",
    },
    # Re-scraped independently by gm-details, by design - not carried over.
    source_unmapped={"phone", "domain", "reviews_count", "average_rating", "street_address", "html"},
    # Injected call context / queue mechanics, not sourced from the list item.
    target_unmapped={"campaign_name", "force_refresh", "ack_token", "attempts"},
)


def test_list_item_to_task_field_integrity() -> None:
    def call_transform(values: dict[str, Any]) -> object:
        item = GoogleMapsListItem.model_validate(
            {
                "place_id": values["place_id"],
                "company_slug": values["company_slug"],
                "name": values["name"],
                "category": values["category"],
                "gmb_url": values["gmb_url"],
                "discovery_phrase": values["discovery_phrase"],
                "discovery_tile_id": values["discovery_tile_id"],
            }
        )
        return item.to_task(campaign_name="turboship")

    source_values = {
        "place_id": _PLACE_ID,
        "company_slug": "test-co",
        "name": "Test Co",
        "category": "Flooring contractor",
        "gmb_url": "https://maps.google.com/x",
        "discovery_phrase": "flooring-contractor",
        "discovery_tile_id": "34.1_-118.4_flooring-contractor",
    }
    assert_transform_field_integrity(LIST_ITEM_TO_TASK, source_values, call_transform)


CATEGORY_MERGE = FieldMap(
    name="build_raw_result_from_details category merge -> GoogleMapsRawResult.First_category",
    source_fields={"detail_page_category", "list_view_category"},
    target_fields={"First_category"},
    merge={
        "First_category": Fallback(
            primary="detail_page_category", fallback_field="list_view_category"
        ),
    },
)


def _call_category_merge(values: dict[str, Any]) -> object:
    details_dict = (
        {"First_category": values["detail_page_category"]}
        if values["detail_page_category"]
        else {}
    )
    result = build_raw_result_from_details(
        details_dict,
        place_id=_PLACE_ID,
        name="Test Co",
        witness_url="https://maps.google.com/x",
        processed_by="test-worker",
        analysis={"is_value_resource": False, "fee_category": None, "rationale": None},
        category=values["list_view_category"],
    )
    assert result is not None
    return result


def test_category_merge_prefers_detail_page_value_when_present() -> None:
    """When the details page DOES find a category, it should win - this
    half of the fallback rule already works today."""
    source_values = {
        "detail_page_category": "Tile store",
        "list_view_category": "Flooring contractor",
    }
    assert_transform_field_integrity(CATEGORY_MERGE, source_values, _call_category_merge)


def test_category_merge_falls_back_to_list_view_value_when_detail_page_empty() -> None:
    source_values = {
        "detail_page_category": None,
        "list_view_category": "Flooring contractor",
    }
    assert_transform_field_integrity(CATEGORY_MERGE, source_values, _call_category_merge)
