from typing import Optional
from pydantic import BaseModel, Field

class ScrapeTask(BaseModel):
    """
    Represents a task to scrape a specific geographic area on Google Maps.
    """
    # Payload
    latitude: float
    longitude: float
    zoom: float
    search_phrase: str
    campaign_name: str
    
    # Optional metadata
    radius_miles: Optional[float] = None # approximate radius covered
    tile_id: Optional[str] = None # For Grid Mode: ID of the 0.1 deg tile
    force_refresh: bool = False
    ttl_days: int = 30
    
    # Queue mechanics (Transient)
    ack_token: Optional[str] = Field(None, exclude=True)
    attempts: int = 0

class GmItemTask(BaseModel):
    """
    Represents a task to scrape details for a specific Google Maps item (Place ID).
    """
    place_id: str
    campaign_name: str
    force_refresh: bool = False
    
    # Queue mechanics
    ack_token: Optional[str] = Field(None, exclude=True)
    attempts: int = 0