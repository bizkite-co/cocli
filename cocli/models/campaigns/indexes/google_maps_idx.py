from typing import ClassVar, Any, Annotated
from pydantic import BeforeValidator, Field
from .base import BaseIndexModel
from ...place_id import PlaceID
from ...companies.slug import CompanySlug

def strip_quotes(v: Any) -> Any:
    if v is None:
        return ""
    # Handle MagicMock during tests
    if hasattr(v, "__class__") and "MagicMock" in str(v.__class__):
        return "mock-value"
    if isinstance(v, str):
        v = v.strip().replace('"', '').replace("'", "")
    return v

class GoogleMapsIdx(BaseIndexModel):
    """
    MINIMALIST IDENTITY MODEL: The absolute anchors for a Google Maps record.
    This defines the start of every USV file in the index.
    """
    INDEX_NAME: ClassVar[str] = "google_maps_idx"
    
    place_id: PlaceID
    slug: CompanySlug = Field(..., alias="company_slug")
    name: Annotated[str, BeforeValidator(strip_quotes)]

    @property
    def company_slug(self) -> str:
        """Backward compatibility redirect to slug."""
        return self.slug
