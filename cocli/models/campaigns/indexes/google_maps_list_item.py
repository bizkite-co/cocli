from pydantic import Field
from typing import Optional
from ...base import BaseUsvModel
from ..queues.gm_details import GmItemTask

class GoogleMapsListItem(BaseUsvModel):
    """
    The discovery model representing a single result in a Google Maps list search.
    Follows Frictionless Data standards.
    """
    # --- FIXED SCHEMA ORDER (Match GmListProcessor trace files) ---
    place_id: str = Field(..., description="Google Place ID")
    company_slug: str = Field(..., description="Generated slug for the business")
    name: str = Field(..., description="Business name from the list view")
    category: Optional[str] = Field(None, description="Primary category from the list view")
    phone: Optional[str] = Field(None, description="Phone number from the list view")
    domain: Optional[str] = Field(None, description="Extracted domain")
    reviews_count: Optional[int] = Field(None, description="Number of reviews")
    average_rating: Optional[float] = Field(None, description="Average rating")
    street_address: Optional[str] = Field(None, description="Street address")
    gmb_url: Optional[str] = Field(None, description="Google Maps URL")
    
    # --- Non-Serialized Metadata (Excluded from to_usv) ---
    discovery_phrase: Optional[str] = Field(None, exclude=True)
    discovery_tile_id: Optional[str] = Field(None, exclude=True)
    html: Optional[str] = Field(None, description="Raw HTML of the list item", exclude=True)

    def to_task(self, campaign_name: str, force_refresh: bool = False) -> GmItemTask:
        """Transforms this list item into a task for the details queue."""
        return GmItemTask(
            place_id=self.place_id,
            campaign_name=campaign_name,
            name=self.name,
            company_slug=self.company_slug,
            force_refresh=force_refresh,
            gmb_url=self.gmb_url,
            discovery_phrase=self.discovery_phrase,
            discovery_tile_id=self.discovery_tile_id
        )
