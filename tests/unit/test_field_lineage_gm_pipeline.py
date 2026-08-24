"""Field-lineage integrity for the gm-list -> gm-details pipeline.

Two edges registered:
  1. GoogleMapsListItem.to_task -> GmItemTask: already correct in production
     code - proves the checker recognizes a good transform, not just flags
     everything.
  2. build_raw_result_from_details' category/rating/reviews_count merges ->
     GoogleMapsRawResult: the documented "fallback when the detail page
     yields nothing" (GmItemTask field docstrings), fixed by task-agent
     ticket recover-dropped-fields (category first, rating/reviews_count as
     its explicitly-scoped follow-up). The category merge test used to
     carry an xfail(strict=True) marker proving the checker caught the bug
     before the fix landed - removed once it passed for real; rating/
     reviews_count never had unimplemented xfail tests, they're new
     alongside their fix.
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
        "gmb_url", "category", "average_rating", "reviews_count",
        "discovery_phrase", "discovery_tile_id", "ack_token", "attempts",
    },
    map={
        "place_id": "place_id",
        "company_slug": "company_slug",
        "name": "name",
        "category": "category",
        "average_rating": "average_rating",
        "reviews_count": "reviews_count",
        "gmb_url": "gmb_url",
        "discovery_phrase": "discovery_phrase",
        "discovery_tile_id": "discovery_tile_id",
    },
    # Re-scraped independently by gm-details, by design - not carried over.
    # (phone/domain/street_address only - average_rating/reviews_count
    # moved to `map` above once they gained the same fallback treatment
    # category already had; see recover-dropped-fields follow-up.)
    source_unmapped={"phone", "domain", "street_address", "html"},
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
                "average_rating": values["average_rating"],
                "reviews_count": values["reviews_count"],
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
        "average_rating": 4.5,
        "reviews_count": 0,
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


RATING_MERGE = FieldMap(
    name="build_raw_result_from_details rating merge -> GoogleMapsRawResult.Average_rating",
    source_fields={"detail_page_rating", "list_view_rating"},
    target_fields={"Average_rating"},
    merge={
        "Average_rating": Fallback(
            primary="detail_page_rating",
            fallback_field="list_view_rating",
            none_means_missing=True,
        ),
    },
)

REVIEWS_COUNT_MERGE = FieldMap(
    name="build_raw_result_from_details reviews_count merge -> GoogleMapsRawResult.Reviews_count",
    source_fields={"detail_page_reviews_count", "list_view_reviews_count"},
    target_fields={"Reviews_count"},
    merge={
        "Reviews_count": Fallback(
            primary="detail_page_reviews_count",
            fallback_field="list_view_reviews_count",
            none_means_missing=True,
        ),
    },
)


def _call_rating_reviews_merge(values: dict[str, Any]) -> object:
    details_dict: dict[str, Any] = {}
    if values["detail_page_rating"] is not None:
        details_dict["Average_rating"] = values["detail_page_rating"]
    if values["detail_page_reviews_count"] is not None:
        details_dict["Reviews_count"] = values["detail_page_reviews_count"]

    result = build_raw_result_from_details(
        details_dict,
        place_id=_PLACE_ID,
        name="Test Co",
        witness_url="https://maps.google.com/x",
        processed_by="test-worker",
        analysis={"is_value_resource": False, "fee_category": None, "rationale": None},
        average_rating=values["list_view_rating"],
        reviews_count=values["list_view_reviews_count"],
    )
    assert result is not None
    return result


def test_rating_reviews_merge_prefers_detail_page_value_when_present() -> None:
    """When the details page DOES find rating/reviews, they should win."""
    source_values = {
        "detail_page_rating": 4.2,
        "list_view_rating": 4.5,
        "detail_page_reviews_count": 88,
        "list_view_reviews_count": 90,
    }
    assert_transform_field_integrity(RATING_MERGE, source_values, _call_rating_reviews_merge)
    assert_transform_field_integrity(REVIEWS_COUNT_MERGE, source_values, _call_rating_reviews_merge)


def test_rating_reviews_merge_falls_back_to_list_view_value_when_detail_page_empty() -> None:
    source_values = {
        "detail_page_rating": None,
        "list_view_rating": 4.5,
        "detail_page_reviews_count": None,
        "list_view_reviews_count": 90,
    }
    assert_transform_field_integrity(RATING_MERGE, source_values, _call_rating_reviews_merge)
    assert_transform_field_integrity(REVIEWS_COUNT_MERGE, source_values, _call_rating_reviews_merge)


def test_reviews_count_zero_is_a_real_value_not_treated_as_missing() -> None:
    """The exact bug `or` would introduce: a business can genuinely have 0
    reviews. That must NOT be treated as "detail page found nothing" and
    overwritten by a (possibly stale/wrong) list-view fallback value."""
    source_values = {
        "detail_page_rating": None,
        "list_view_rating": 4.5,
        "detail_page_reviews_count": 0,
        "list_view_reviews_count": 90,
    }
    assert_transform_field_integrity(REVIEWS_COUNT_MERGE, source_values, _call_rating_reviews_merge)
