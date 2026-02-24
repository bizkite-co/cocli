from typing import Optional, ClassVar
from pydantic import Field

from .base import BaseIndexModel

class LifecycleItem(BaseIndexModel):
    """
    Represents the progression of a lead through the automated enrichment pipeline.
    """
    INDEX_NAME: ClassVar[str] = "lifecycle"
    RESOURCE_PATH: ClassVar[str] = "lifecycle.usv"

    place_id: str = Field(..., description="Google Maps Place ID")
    scraped_at: Optional[str] = Field(None, description="ISO date of list discovery")
    details_at: Optional[str] = Field(None, description="ISO date of detail scraping")
    enqueued_at: Optional[str] = Field(None, description="ISO date of website enrichment queuing")
    enriched_at: Optional[str] = Field(None, description="ISO date of website enrichment completion")
