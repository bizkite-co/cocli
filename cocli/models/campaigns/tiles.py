from __future__ import annotations
from typing import ClassVar, Optional
from ..base import BaseUsvModel
from pydantic import Field
from ...core.geo_types import LatScale1, LonScale1


class TileRecord(BaseUsvModel):
    """
    Represents a single geographic tile in the discovery-gen grid.
    Output of Stage 1 (generate_tiles).
    """

    id: str = Field(..., description="Unique tile identifier (0.1-degree grid cell ID, e.g., '25.0_-79.9')")
    center_lat: LatScale1 = Field(..., description="Center latitude of the tile")
    center_lon: LonScale1 = Field(..., description="Center longitude of the tile")
    zoom_level: Optional[int] = Field(None, description="Zoom level of the tile (optional)")

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
