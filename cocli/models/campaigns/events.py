# POLICY: frictionless-data-policy-enforcement
from datetime import datetime
from typing import Optional, List
from pydantic import Field
from ..base import BaseUsvModel

class Event(BaseUsvModel):
    """
    Standard model for Fullertonian community events.
    Sharded by month/week in the campaign's events queue.
    """
    # Authoritative Sequence for USV
    start_time: datetime = Field(..., description="ISO datetime of the event")
    host_slug: str = Field(..., description="Slug of the hosting organization/venue")
    event_slug: str = Field(..., description="Slug of the event name")
    name: str = Field(..., description="Full human-readable event name")
    host_name: str = Field(..., description="Full human-readable host name")
    
    location: Optional[str] = None
    fee: Optional[str] = "Free"
    description: Optional[str] = None
    url: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    
    # Metadata
    campaign_name: str = "fullertonian"
    source_url: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now())
    
    def get_wal_filename(self) -> str:
        """
        Generates the standard filename for the WAL:
        ISO_DATETIME_host-slug_event-slug.json
        """
        ts = self.start_time.strftime("%Y%m%dT%H%M%S")
        return f"{ts}_{self.host_slug}_{self.event_slug}.json"
