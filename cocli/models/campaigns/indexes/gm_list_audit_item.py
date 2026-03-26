from pydantic import Field
from typing import Optional, ClassVar
from ...base import BaseUsvModel, ResourcePathPolicy


class GmListAuditItem(BaseUsvModel):
    """
    Audit item for gm-list HTML scraping quality control.
    Used to verify and extract rating/review data from raw HTML files.
    """

    SCHEMA_UPDATED_AT: ClassVar[str] = "2026-03-25T00:00:00+00:00"
    RESOURCE_PATH_PATTERN: ClassVar[ResourcePathPolicy] = ResourcePathPolicy.SPECIFIC

    place_id: str = Field(
        ..., min_length=26, max_length=29, description="Google Place ID"
    )
    name: str = Field(..., min_length=1, max_length=100, description="Business name")
    average_rating: Optional[float] = Field(
        None, ge=0.0, le=5.0, description="Average rating (0-5)"
    )
    reviews_count: Optional[int] = Field(None, ge=0, description="Number of reviews")
    gmb_url: Optional[str] = Field(None, min_length=20, description="Google Maps URL")
