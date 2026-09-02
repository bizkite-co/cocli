from pydantic import BaseModel

class TileStatusResult(BaseModel):
    """map-tile has no processing phase (removed 2026-08-09) - it's a pure
    tile registry, no staging/throttling job of its own."""
    pending_count: int
    completed_count: int

class MissionReconciliationResult(BaseModel):
    """Mission (discovery-gen/completed) vs receipts (gm-list/completed/results)
    and pending (gm-list/pending) vs receipts, for gm-list's queue."""
    campaign_name: str
    mission_total: int
    receipt_total: int
    unscraped_count: int
    unscraped_ids: list[str]
    orphaned_receipt_count: int
    orphaned_receipt_ids: list[str]
    pending_total: int
    stale_pending_count: int
    stale_pending_ids: list[str]
    truly_pending_count: int
    truly_pending_ids: list[str]
