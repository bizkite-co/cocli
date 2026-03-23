from pydantic import Field
from typing import Optional, ClassVar
from ...base import BaseUsvModel, ResourcePathPolicy


class CompactProspect(BaseUsvModel):
    """
    Standardized model for compacted Google Maps results (10 columns).
    Used for reliable filtering of top prospects.
    """

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    RESOURCE_PATH_PATTERN: ClassVar[ResourcePathPolicy] = ResourcePathPolicy.SPECIFIC

    place_id: str = Field(..., min_length=26, max_length=29)
    company_slug: str = Field(..., min_length=3, max_length=100)
    name: str = Field(..., min_length=1, max_length=100)
    category: Optional[str] = Field(None, min_length=2, max_length=100)
    phone: Optional[str] = Field(None, min_length=10, max_length=15)
    domain: Optional[str] = Field(None, min_length=3, max_length=100)
    reviews_count: Optional[int] = Field(None, ge=0)
    average_rating: Optional[float] = Field(None, ge=0.0, le=5.0)
    street_address: Optional[str] = Field(None, min_length=5, max_length=100)
    gmb_url: Optional[str] = Field(None, min_length=20)
