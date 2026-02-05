from pydantic import BaseModel, Field
from typing import Optional

class GmItemTask(BaseModel):
    """
    Represents a task to scrape details for a specific Google Maps item (Place ID).
    This is the bridge between gm-list and gm-details.
    """
    place_id: str
    campaign_name: str
    name: str
    company_slug: str
    force_refresh: bool = False
    
    # Queue mechanics (Transient)
    ack_token: Optional[str] = Field(default=None, exclude=True)
    attempts: int = 0
