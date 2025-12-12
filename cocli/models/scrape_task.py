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
    force_refresh: bool = False
    ttl_days: int = 30
    
    # Queue mechanics (Transient)
    ack_token: Optional[str] = Field(None, exclude=True)
    attempts: int = 0