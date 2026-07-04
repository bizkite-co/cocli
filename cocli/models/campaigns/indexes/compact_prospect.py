from pydantic import Field
from typing import Optional, ClassVar
from ...base import BaseUsvModel, ResourcePathPolicy
from ...phone import OptionalPhone
from ...company_name import OptionalCompanyName
from ...company_address import OptionalCompanyAddress


class CompactProspect(BaseUsvModel):
    """
    Standardized model for compacted Google Maps results (10 columns).
    Used for reliable filtering of top prospects.
    """

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    RESOURCE_PATH_PATTERN: ClassVar[ResourcePathPolicy] = ResourcePathPolicy.SPECIFIC

    place_id: str = Field(..., min_length=26, max_length=29)
    company_slug: str = Field(..., min_length=3, max_length=100)
    name: OptionalCompanyName = Field(None)
    category: Optional[str] = Field(None, min_length=2, max_length=100)
    phone: OptionalPhone = Field(None)
    domain: Optional[str] = Field(None, min_length=3, max_length=100)
    reviews_count: Optional[int] = Field(None, ge=0)
    average_rating: Optional[float] = Field(None, ge=0.0, le=5.0)
    street_address: OptionalCompanyAddress = Field(None)
    gmb_url: Optional[str] = Field(None, min_length=20)
