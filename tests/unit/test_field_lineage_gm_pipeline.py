"""Field-lineage integrity for the gm-list -> gm-details pipeline.

One edge registered: GoogleMapsListItem.to_task -> GmItemTask.

An earlier version of this file also registered CATEGORY_MERGE/RATING_MERGE/
REVIEWS_COUNT_MERGE edges for build_raw_result_from_details, asserting that
category/average_rating/reviews_count were threaded from gm-list's list-view
data through GmItemTask as fallbacks when the detail page's own parse came up
empty (task-agent ticket recover-dropped-fields). That fallback-via-queue-
payload design was reverted: gm-details now always writes what the detail
page actually found (None/empty if it found nothing), and recovery of a
field the detail page misses is left to GoogleMapsProspect.merge_with_existing
(never overwrite with null/empty) and compact_gm_list_results()'s COALESCE
against gm-list's own durable results/ files (data-quality-incidents/003) -
not to a hint carried through the queue message. Carrying the hint was found
to be solving a race (gm-list's results file rotating away before
compaction) that doesn't currently exist, since the only code that ever
deletes those files is disabled in production
(operation_service.py's op_sanitize_discovery).
"""

from typing import Any

from cocli.core.audit.field_lineage import FieldMap, assert_transform_field_integrity
from cocli.models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem

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
        "gmb_url", "discovery_phrase", "discovery_tile_id", "ack_token",
        "attempts",
    },
    map={
        "place_id": "place_id",
        "company_slug": "company_slug",
        "name": "name",
        "gmb_url": "gmb_url",
        "discovery_phrase": "discovery_phrase",
        "discovery_tile_id": "discovery_tile_id",
    },
    # Re-scraped independently by gm-details, by design - not carried over.
    # category/average_rating/reviews_count live here too now: gm-details
    # writes its own parse (or None) for these and leans on
    # merge_with_existing + compact_gm_list_results() for recovery, rather
    # than receiving a list-view hint through the task payload.
    source_unmapped={
        "phone", "domain", "street_address", "html",
        "category", "average_rating", "reviews_count",
    },
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
