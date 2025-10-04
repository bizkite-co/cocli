from typing import Optional
from pydantic import BaseModel

class GeocodeData(BaseModel):
    version: int = 1
    latitude: float
    longitude: float
    address: Optional[str] = None
    zip_code: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
