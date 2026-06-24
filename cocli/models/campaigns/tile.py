from typing import ClassVar
from ..base import BaseUsvModel
from pydantic import Field
from ...core.geo_types import LatScale1, LonScale1


class TileRecord(BaseUsvModel):
    """
    Atomic work unit for tile-queue.
    Represents one tile with all its search phrases ready for scraping.
    Used in tile-queue/pending/tiles/*.usv files (one file per tile).
    """
    tile_id: str = Field(..., description="Southwest corner 0.1-degree grid ID (e.g., 25.0_-79.9)")
    search_phrase: str = Field(..., description="Slugified search query")
    latitude: LatScale1 = Field(..., description="Target latitude for the search")
    longitude: LonScale1 = Field(..., description="Target longitude for the search")

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
