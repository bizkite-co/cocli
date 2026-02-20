from pydantic import BaseModel, Field
from typing import Optional
from ..queues.gm_details import GmItemTask

class GoogleMapsListItem(BaseModel):
    """
    The discovery model representing a single result in a Google Maps list search.
    """
    place_id: str = Field(..., description="Google Place ID")
    name: str = Field(..., description="Business name from the list view")
    company_slug: str = Field(..., description="Generated slug for the business")
    phone: Optional[str] = Field(None, description="Phone number from the list view")
    gmb_url: Optional[str] = None
    discovery_phrase: Optional[str] = None
    discovery_tile_id: Optional[str] = None

    def to_task(self, campaign_name: str, force_refresh: bool = False) -> GmItemTask:
        """Transforms this list item into a task for the details queue."""
        return GmItemTask(
            place_id=self.place_id,
            campaign_name=campaign_name,
            name=self.name,
            company_slug=self.company_slug,
            force_refresh=force_refresh,
            discovery_phrase=self.discovery_phrase,
            discovery_tile_id=self.discovery_tile_id
        )
