from pydantic import BaseModel
from typing import List, Optional

class ProcessingTileDetail(BaseModel):
    tile_name: str
    worker_id: Optional[str] = None
    age_min: Optional[float] = None
    ttl_min: Optional[float] = None
    status: Optional[str] = None
    style: Optional[str] = None
    error: Optional[str] = None
    no_lease: Optional[bool] = None

class TileStatusResult(BaseModel):
    pending_count: int
    processing_count: int
    completed_count: int
    processing_tiles_details: List[ProcessingTileDetail]
    expired_count: int
