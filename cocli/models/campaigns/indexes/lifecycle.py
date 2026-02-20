from typing import Optional, ClassVar
from pydantic import Field

from ....core.utils import UNIT_SEP
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

    def to_usv(self) -> str:
        """Serializes to a single USV line."""
        cols = [
            self.place_id,
            self.scraped_at or "",
            self.details_at or "",
            self.enqueued_at or "",
            self.enriched_at or ""
        ]
        return UNIT_SEP.join(cols) + "\n"
