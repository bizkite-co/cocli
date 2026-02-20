from typing import ClassVar, Any, Annotated
from pydantic import BeforeValidator
from .base import BaseIndexModel
from ...place_id import PlaceID
from ...companies.slug import CompanySlug

def strip_quotes(v: Any) -> str:
    if isinstance(v, str):
        v = v.strip()
        if v.startswith('"') and v.endswith('"'):
            v = v[1:-1].strip()
        if v.startswith("'") and v.endswith("'"):
            v = v[1:-1].strip()
    return str(v)

class GoogleMapsIdx(BaseIndexModel):
    """
    MINIMALIST IDENTITY MODEL: The absolute anchors for a Google Maps record.
    This defines the start of every USV file in the index.
    """
    INDEX_NAME: ClassVar[str] = "google_maps_idx"
    
    place_id: PlaceID
    company_slug: CompanySlug
    name: Annotated[str, BeforeValidator(strip_quotes)]
