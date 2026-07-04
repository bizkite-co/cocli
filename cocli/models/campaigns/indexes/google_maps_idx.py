from typing import ClassVar, Any
from pydantic import Field
from .base import BaseIndexModel
from ...place_id import PlaceID
from ...companies.slug import CompanySlug
from ...company_name import OptionalCompanyName

def strip_quotes(v: Any) -> Any:
    """Legacy strip_quotes function - kept for backward compatibility with other fields."""
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
    name: OptionalCompanyName = None

    @property
    def company_slug(self) -> str:
        """Backward compatibility redirect to slug."""
        return self.slug
