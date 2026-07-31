"""
CompactProspect to GoogleMapsProspect Transformer.

CompactProspect also models a historical prospect shape found in turboship's
WAL backlog: rows written positionally into the current GoogleMapsProspect
column layout by an old migration/recovery script, populating only
place_id/name/phone/street_address/domain/reviews_count/average_rating/
gmb_url/category and leaving every other field - including slug,
created_at, updated_at, version, and company_hash - blank. Those blanks
fail GoogleMapsProspect's own validation (slug has a min_length, datetimes
can't parse ""), so this backfills the identity/metadata fields a real
GoogleMapsProspect.to_usv() write would never have left empty.
"""

from cocli.core.text_utils import calculate_company_hash, slugify
from cocli.models.campaigns.indexes.compact_prospect import CompactProspect
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect


def transform_compact_prospect_to_google_maps_prospect(
    legacy: CompactProspect,
) -> GoogleMapsProspect:
    """Backfills identity/metadata fields a legacy-shaped row never had.

    created_at/updated_at are intentionally omitted rather than backfilled
    with a guess - the real scrape time isn't recoverable from this shape,
    so GoogleMapsProspect's own default_factory (now()) fills them, and
    processed_by marks the row as backfilled rather than freshly scraped.
    """
    name = str(legacy.name) if legacy.name else None
    street_address = str(legacy.street_address) if legacy.street_address else None

    # slugify() is ASCII-only (ignores names in styled/non-Latin Unicode,
    # e.g. mathematical-bold characters), so it can legitimately reduce a
    # real name to "" - fall back to place_id (always >= 26 chars) whenever
    # the result is shorter than CompanySlug's min_length=3, not just when
    # name itself is missing.
    slug_candidate = slugify(name) if name else ""
    slug = slug_candidate if len(slug_candidate) >= 3 else legacy.place_id

    return GoogleMapsProspect(  # type: ignore[call-arg]
        place_id=legacy.place_id,
        slug=slug,
        name=legacy.name,
        phone=legacy.phone,
        street_address=legacy.street_address,
        domain=legacy.domain,
        reviews_count=legacy.reviews_count,
        average_rating=legacy.average_rating,
        gmb_url=legacy.gmb_url,
        category=legacy.category,
        company_hash=calculate_company_hash(name, street_address, None),
        processed_by="legacy-backfill-compact-prospect",
        version=1,
    )
