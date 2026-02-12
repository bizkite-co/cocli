from typing import ClassVar
from .base_index import BaseIndexModel
from .place_id import PlaceID
from .company_slug import CompanySlug

class GoogleMapsIdx(BaseIndexModel):
    """
    MINIMALIST IDENTITY MODEL: The absolute anchors for a Google Maps record.
    This defines the start of every USV file in the index.
    """
    INDEX_NAME: ClassVar[str] = "google_maps_idx"
    
    place_id: PlaceID
    company_slug: CompanySlug
    name: str
