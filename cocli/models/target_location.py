from typing import Optional
from pydantic import BaseModel, Field, field_serializer

class TargetLocation(BaseModel):
    name: str = Field(alias="name")
    lat: float
    lon: float
    city: Optional[str] = None
    state: Optional[str] = None
    company_slug: Optional[str] = None
    csv_name: Optional[str] = None
    saturation_score: Optional[float] = 0.0

    model_config = {
        "populate_by_name": True,
        "extra": "ignore" 
    }

    @field_serializer('lat', 'lon')
    def serialize_coordinates(self, v: float, _info):
        return round(v, 5)
