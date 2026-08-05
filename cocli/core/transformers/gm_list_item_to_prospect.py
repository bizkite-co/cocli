"""GoogleMapsListItem to GoogleMapsProspect Transformer.

Lets the gm-list scraper's domain-bypass path (worker_service.py
_run_scrape_task_loop) build a real GoogleMapsProspect and persist it via
ProspectsIndexManager.add_to_wal() - instead of only pushing a lightweight
QueueMessage to the enrichment queue, which left the discovery invisible to
the prospects checkpoint until someone manually ran compact_gm_list_results().
"""

from cocli.models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect


def transform_gm_list_item_to_google_maps_prospect(
    item: GoogleMapsListItem,
) -> GoogleMapsProspect:
    """Pure from-model-to-model transform (ADR-001).

    Every field GoogleMapsListItem captures maps directly by name onto
    GoogleMapsProspect; company_slug is the one rename (-> slug, via
    GoogleMapsIdx's `alias="company_slug"`). source_unmapped: html (no
    destination field on the prospect model - dropped, matching how html
    is already discarded everywhere else in this pipeline).
    """
    return GoogleMapsProspect(  # type: ignore[call-arg]
        place_id=item.place_id,
        company_slug=item.company_slug,  # alias for `slug` (GoogleMapsIdx)
        name=item.name,
        category=item.category,
        phone_1=item.phone,  # alias for `phone` (GoogleMapsPlace)
        domain=item.domain,
        reviews_count=item.reviews_count,
        average_rating=item.average_rating,
        street_address=item.street_address,
        gmb_url=item.gmb_url,
        discovery_phrase=item.discovery_phrase,
        discovery_tile_id=item.discovery_tile_id,
    )
