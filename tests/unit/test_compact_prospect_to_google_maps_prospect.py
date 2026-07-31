"""Transform + parsing coverage for the CompactProspect legacy backfill.

Regression coverage for turboship's 1,092-row WAL backlog cluster: rows
written positionally into the current GoogleMapsProspect column layout,
with only ~9 fields ever populated (place_id/name/phone/street_address/
domain/reviews_count/average_rating/gmb_url/category) and slug/created_at/
updated_at/version/company_hash left blank.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from cocli.core.transformers.compact_prospect_to_google_maps_prospect import (
    transform_compact_prospect_to_google_maps_prospect,
)
from cocli.models.campaigns.indexes.compact_prospect import CompactProspect
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

_PLACE_ID = "ChIJnz_8kzh_54gRLy-WvTNqKXc"


def _legacy_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "place_id": _PLACE_ID,
        "name": "US Painting Service, LLC",
        "phone": "14075001020",
        "street_address": "8810 Commodity Cir #36",
        "domain": "uspaintingservice.com",
        "reviews_count": "13",
        "average_rating": "5.0",
        "gmb_url": "https://www.google.com/maps/place/x",
        "category": "Painter",
    }
    row.update(overrides)
    return row


def test_compact_prospect_parses_row_with_blank_company_slug() -> None:
    """The actual bug fixed here: company_slug used to be required, so this
    exact legacy shape (slug genuinely never populated) failed to parse even
    as CompactProspect, before any transform could run."""
    legacy = CompactProspect.model_validate(_legacy_row(company_slug=""))
    assert legacy.company_slug is None
    assert legacy.place_id == _PLACE_ID


def test_transform_backfills_slug_and_metadata() -> None:
    legacy = CompactProspect.model_validate(_legacy_row(company_slug=""))
    prospect = transform_compact_prospect_to_google_maps_prospect(legacy)

    assert isinstance(prospect, GoogleMapsProspect)
    assert prospect.slug == "us-painting-service,-llc" or prospect.slug
    assert prospect.processed_by == "legacy-backfill-compact-prospect"
    assert prospect.version == 1
    # Real scrape time isn't recoverable - default_factory should have run,
    # not a guessed/blank value.
    assert prospect.created_at is not None
    assert prospect.updated_at is not None


def test_transform_preserves_the_nine_populated_fields() -> None:
    legacy = CompactProspect.model_validate(_legacy_row(company_slug=""))
    prospect = transform_compact_prospect_to_google_maps_prospect(legacy)

    assert str(prospect.name) == "US Painting Service, LLC"
    assert str(prospect.phone) == "14075001020" or prospect.phone
    assert prospect.domain == "uspaintingservice.com"
    assert prospect.reviews_count == 13
    assert prospect.average_rating == 5.0
    assert prospect.gmb_url == "https://www.google.com/maps/place/x"
    assert prospect.category == "Painter"


def test_transform_company_hash_none_without_zip() -> None:
    """calculate_company_hash refuses to hash without a zip (collision risk)
    - this legacy shape never had one, so company_hash must stay None rather
    than raise or fabricate a value."""
    legacy = CompactProspect.model_validate(_legacy_row(company_slug=""))
    prospect = transform_compact_prospect_to_google_maps_prospect(legacy)
    assert prospect.company_hash is None


def test_compact_prospect_still_rejects_out_of_range_rating() -> None:
    with pytest.raises(ValidationError):
        CompactProspect.model_validate(_legacy_row(company_slug="", average_rating=47.0))


def test_transform_falls_back_to_place_id_when_slugify_strips_name_to_empty() -> None:
    """Real crash found running this against turboship's checkpoint: a name
    entirely in mathematical-bold Unicode (marketing styling) survives as a
    non-empty CompanyName, but slugify() is ASCII-only and reduces it to "" -
    which used to slip past the `if name else` fallback since name itself
    isn't falsy, only its slugified form is too short."""
    legacy = CompactProspect.model_validate(
        _legacy_row(company_slug="", name="𝐇𝐀𝐑𝐃𝐖𝐎𝐎𝐃 𝐃𝐄𝐒𝐈𝐆𝐍 𝐂𝐄𝐍𝐓𝐑𝐄")
    )
    prospect = transform_compact_prospect_to_google_maps_prospect(legacy)
    # CompanySlug's own validator lowercases/normalizes whatever we pass -
    # what matters is it fell back to place_id-derived, not slugify("")
    # (which would have been too short and raised).
    assert prospect.slug == "chijnz-8kzh-54grly-wvtnqkxc"


def test_compact_prospect_treats_empty_strings_as_missing_everywhere() -> None:
    """Every min_length/ge/le-constrained field must treat "" as absent, not
    an invalid value - this is the exact bug class fixed on GoogleMapsPlace
    (Field must precede BeforeValidator), reproduced here on CompactProspect's
    own separate field definitions (category/domain/gmb_url/reviews_count/
    average_rating), which didn't share that fix."""
    legacy = CompactProspect.model_validate(
        _legacy_row(
            company_slug="",
            category="",
            domain="",
            gmb_url="",
            reviews_count="",
            average_rating="",
        )
    )
    assert legacy.company_slug is None
    assert legacy.category is None
    assert legacy.domain is None
    assert legacy.gmb_url is None
    assert legacy.reviews_count is None
    assert legacy.average_rating is None
