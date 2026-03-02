from typing import ClassVar
from ..base import BaseUsvModel
from pydantic import Field, field_serializer

class MissionTask(BaseUsvModel):
    """
    Standardized model for GM List mission tasks and pending scrape frontier.
    Used for both master (mission.usv) and frontier (pending_scrape_total.usv).
    """
    tile_id: str = Field(..., description="Southwest corner 0.1-degree grid ID (e.g., 25.0_-79.9)")
    search_phrase: str = Field(..., description="Slugified search query")
    latitude: float = Field(..., description="Target latitude for the search")
    longitude: float = Field(..., description="Target longitude for the search")
    
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    @field_serializer("latitude", "longitude")
    def serialize_float(self, v: float) -> str:
        return f"{v:.6f}"
