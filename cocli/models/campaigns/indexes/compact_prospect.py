from __future__ import annotations
from pydantic import BeforeValidator, Field
from typing import Annotated, Any, Optional, ClassVar
from ...base import BaseUsvModel, ResourcePathPolicy
from ...phone import OptionalPhone
from ...company_name import OptionalCompanyName
from ...company_address import OptionalCompanyAddress
from .google_maps_place import safe_float, safe_int


def _empty_to_none(v: Any) -> Any:
    return None if v == "" else v


class CompactProspect(BaseUsvModel):
    """
    Standardized model for compacted Google Maps results (10 columns).
    Used for reliable filtering of top prospects.

    Also doubles as the parser for a historical prospect shape found in
    turboship's WAL backlog: rows written positionally into the current
    GoogleMapsProspect column layout by an old migration/recovery script,
    with only these 9-10 fields ever populated and company_slug/slug left
    blank. See transformers/compact_prospect_to_google_maps_prospect.py.
    company_slug is optional for exactly that reason - real CompactProspect
    output always has it; this legacy shape never did.
    """

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    RESOURCE_PATH_PATTERN: ClassVar[ResourcePathPolicy] = ResourcePathPolicy.SPECIFIC

    # Field(min_length=/ge=/le=) must precede BeforeValidator in the Annotated
    # stack, same ordering fix as GoogleMapsPlace.average_rating/reviews_count -
    # the reverse order makes "" raise before the empty-to-None coercion runs.
    place_id: str = Field(..., min_length=26, max_length=29)
    company_slug: Annotated[
        Optional[str], Field(min_length=3, max_length=100), BeforeValidator(_empty_to_none)
    ] = None
    name: OptionalCompanyName = Field(None)
    category: Annotated[
        Optional[str], Field(min_length=2, max_length=100), BeforeValidator(_empty_to_none)
    ] = None
    phone: OptionalPhone = Field(None)
    domain: Annotated[
        Optional[str], Field(min_length=3, max_length=100), BeforeValidator(_empty_to_none)
    ] = None
    reviews_count: Annotated[Optional[int], Field(ge=0), BeforeValidator(safe_int)] = None
    average_rating: Annotated[
        Optional[float], Field(ge=0.0, le=5.0), BeforeValidator(safe_float)
    ] = None
    street_address: OptionalCompanyAddress = Field(None)
    gmb_url: Annotated[
        Optional[str], Field(min_length=20), BeforeValidator(_empty_to_none)
    ] = None
