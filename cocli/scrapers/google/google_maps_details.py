from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from playwright.async_api import Page

from cocli.models.campaigns.raw_witness import RawWitness

from ..gm_details_scraper import GoogleMapsDetailsScraper

if TYPE_CHECKING:
    from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
    from cocli.models.campaigns.indexes.google_maps_raw import GoogleMapsRawResult

logger = logging.getLogger(__name__)

async def capture_google_maps_raw(
    page: Page,
    place_id: str,
    campaign_name: str,
    processed_by: str = "local-scraper",
    debug: bool = False
) -> Optional[RawWitness]:
    """
    Navigates to a Google Maps place and captures the raw HTML and basic metadata.
    Uses the GoogleMapsDetailsScraper state machine for robust execution.
    """
    scraper = GoogleMapsDetailsScraper(page, campaign_name, processed_by)
    return await scraper.scrape(place_id)

def build_raw_result_from_details(
    details_dict: dict[str, Any],
    *,
    place_id: str,
    name: Optional[str],
    witness_url: str,
    processed_by: str,
    analysis: dict[str, Any],
) -> Optional[GoogleMapsRawResult]:
    """Pure merge point: parsed detail-page dict (+ scrape context) -> GoogleMapsRawResult.

    Extracted from scrape_google_maps_details() so the field-lineage
    integrity checker (cocli/core/audit/field_lineage.py) can exercise this
    merge directly, without a live page/network.

    Fields the detail page doesn't find are written as None/empty here, on
    purpose - never backfilled with a gm-list list-view "hint" carried
    through GmItemTask. Recovery for a field this scrape misses is the job
    of GoogleMapsProspect.merge_with_existing() (never overwrite with
    null/empty) and compact_gm_list_results()'s COALESCE against gm-list's
    own durable results (see data-quality-incidents/003), not this merge
    point. See task-agent ticket recover-dropped-fields for why an earlier
    version of this function threaded category/average_rating/reviews_count
    through as fallbacks, and why that was reverted.
    """
    from cocli.core.text_utils import parse_postal_address
    from cocli.models.campaigns.indexes.google_maps_raw import GoogleMapsRawResult

    final_name = details_dict.get("Name") or name
    if not final_name:
        logger.error(f"IDENTITY SHIELD: No name found for {place_id} and no fallback provided. Blocking save.")
        return None
    full_address = details_dict.get("Full_Address", "")
    # Address components from this scrape's own detail page. parse_gmb_page
    # already captured Latitude/Longitude/Coordinates from the witness URL
    # (the page is this scrape's own evidence, not a foreign hint - see the    # recover-dropped-fields rule below); the string components come from the
    # shared postal parser when the page didn't provide them explicitly.
    addr = parse_postal_address(full_address) if full_address else {}
    street_address = details_dict.get("Street_Address") or addr.get("street_address")
    city = details_dict.get("City") or addr.get("city")
    zip_code = details_dict.get("Zip") or addr.get("zip")
    state = details_dict.get("State") or addr.get("state")
    country = details_dict.get("Country") or addr.get("country")

    # Timezone: the Maps page gives no IANA zone. Derive it offline from the
    # point (timezonefinder, local data - no network) when the page itself
    # didn't supply one. Only fills-empty here; merge_with_existing on the
    # prospect and the fill-empty company step never overwrite a set value.
    timezone = details_dict.get("Timezone")
    if not timezone and details_dict.get("Latitude") and details_dict.get("Longitude"):
        from cocli.utils.timezone_geo import timezone_at

        timezone = timezone_at(details_dict["Latitude"], details_dict["Longitude"])

    return GoogleMapsRawResult(
        Place_ID=place_id,
        Name=final_name,
        Full_Address=full_address,
        Street_Address=street_address,
        City=city,
        Zip=zip_code,
        State=state,
        Country=country,
        Timezone=timezone,
        Latitude=details_dict.get("Latitude"),
        Longitude=details_dict.get("Longitude"),
        Coordinates=details_dict.get("Coordinates"),
        Website=details_dict.get("Website", ""),
        Phone_1=details_dict.get("Phone", ""),
        First_category=details_dict.get("First_category"),
        Second_category=details_dict.get("Second_category"),
        Reviews_count=details_dict.get("Reviews_count"),
        Average_rating=details_dict.get("Average_rating"),
        Reviews=details_dict.get("Reviews"),
        Thumbnail_URL=details_dict.get("Thumbnail_URL"),
        GMB_URL=witness_url,
        processed_by=processed_by,
        is_value_resource=analysis["is_value_resource"],
        fee_category=analysis["fee_category"],
        rationale=analysis["rationale"],
    )


async def scrape_google_maps_details(
    page: Page,
    place_id: str,
    campaign_name: str,
    name: Optional[str] = None,
    company_slug: Optional[str] = None,
    debug: bool = False
) -> Optional[GoogleMapsProspect]:
    """
    Scrapes full details for a given Google Maps Place ID.
    Uses the state machine for capture and then parses the result.
    """
    from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
    from cocli.scrapers.google.google_maps_gmb_parser import parse_gmb_page

    # Execute state-machine capture
    witness = await capture_google_maps_raw(page, place_id, campaign_name, debug=debug)
    if not witness:
        return None

    # Parse with GMB parser (witness URL supplies this page's own coordinates)
    details_dict = parse_gmb_page(witness.html, witness_url=witness.url, debug=debug)

    # --- Resource Discovery Analysis ---
    from ..resource_analyzer import analyze_resource_value
    analysis = analyze_resource_value(
        name=details_dict.get("Name") or name or "",
        category=details_dict.get("First_category") or "",
        description=details_dict.get("Description") or "", # We might need to extract this too
        reviews=details_dict.get("Reviews") or ""
    )

    raw_result = build_raw_result_from_details(
        details_dict,
        place_id=place_id,
        name=name,
        witness_url=witness.url,
        processed_by=witness.processed_by,
        analysis=analysis,
    )
    if raw_result is None:
        return None

    try:
        prospect = GoogleMapsProspect.from_raw(raw_result)
        if company_slug:
            prospect.slug = company_slug
        return prospect
    except Exception as val_err:
        logger.error(f"IDENTITY SHIELD: Validation failed for {place_id}: {val_err}")
        return None
