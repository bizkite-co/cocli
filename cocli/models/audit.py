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

class MissionReconciliationResult(BaseModel):
    """Mission (discovery-gen/completed) vs receipts (gm-list/completed/results)
    and pending (gm-list/pending) vs receipts, for gm-list's queue."""
    campaign_name: str
    mission_total: int
    receipt_total: int
    unscraped_count: int
    unscraped_ids: List[str]
    orphaned_receipt_count: int
    orphaned_receipt_ids: List[str]
    pending_total: int
    stale_pending_count: int
    stale_pending_ids: List[str]
    truly_pending_count: int
    truly_pending_ids: List[str]
