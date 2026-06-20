from ..base import BaseUsvModel
from pydantic import Field
from ...core.geo_types import LatScale1, LonScale1


class TargetLocationRecord(BaseUsvModel):
    """
    Represents a single target location for discovery-gen.
    Input for Stage 1 (generate_tiles).

    All lat/lon values are normalized to LatScale1/LonScale1 (1 decimal place).
    """

    name: str = Field(..., description="Location name or label")
    latitude: LatScale1 = Field(..., description="Latitude (normalized to 1 decimal place)")
    longitude: LonScale1 = Field(..., description="Longitude (normalized to 1 decimal place)")
