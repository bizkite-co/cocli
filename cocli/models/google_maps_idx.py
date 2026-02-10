from pydantic import Field
from typing import Optional, ClassVar
from .base_index import BaseIndexModel

class GoogleMapsIdx(BaseIndexModel):
    """
    MINIMALIST IDENTITY MODEL: The absolute anchors for a Google Maps record.
    This defines the start of every USV file in the index.
    """
    INDEX_NAME: ClassVar[str] = "google_maps_prospects"
    
    place_id: str = Field(..., description="Google Maps Place ID")
    company_slug: str = Field(..., min_length=3, description="Clean filesystem-friendly identifier")
    name: str = Field(..., min_length=3, description="Business name")
