from typing import ClassVar
from ..base import BaseUsvModel
from pydantic import Field
from ...core.geo_types import LatScale6, LonScale6

class MissionTask(BaseUsvModel):
    """
    Standardized model for GM List mission tasks and pending scrape frontier.
    Used for both master (mission.usv) and frontier (frontier.usv).
    """
    tile_id: str = Field(..., description="Southwest corner 0.1-degree grid ID (e.g., 25.0_-79.9)")
    search_phrase: str = Field(..., description="Slugified search query")
    latitude: LatScale6 = Field(..., description="Target latitude for the search")
    longitude: LonScale6 = Field(..., description="Target longitude for the search")
    
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
