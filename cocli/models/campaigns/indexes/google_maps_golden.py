# POLICY: frictionless-data-policy-enforcement
from typing import ClassVar, Optional
from pathlib import Path
from pydantic import Field
from .base import BaseIndexModel

class GoogleMapsGoldenItem(BaseIndexModel):
    """
    Represents an entry in the Google Maps Golden Set for testing.
    Standardized columns for parser validation.
    """
    INDEX_NAME: ClassVar[str] = "google_maps_golden"
    
    name: str = Field(..., description="Business name")
    address: Optional[str] = Field(None, description="Full address")
    phone: Optional[str] = Field(None, description="Phone number")
    website: Optional[str] = Field(None, description="Website URL")
    place_id: str = Field(..., description="Google Maps Place ID")
    search_phrase: str = Field(..., description="The phrase used to find it")
    lat: float = Field(..., description="Latitude")
    lon: float = Field(..., description="Longitude")

    @classmethod
    def save_datapackage(cls, path: Path, resource_name: str = "google_maps_golden", resource_path: str = "golden_set.usv", force: bool = False) -> None:
        """Saves the datapackage.json to the specified directory."""
        super().save_datapackage(path, resource_name, resource_path, force=force)
