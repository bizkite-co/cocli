from typing import Optional
from pathlib import Path
from pydantic import BaseModel, Field
from ..core.paths import paths
from ..core.ordinant import QueueName, get_shard

class ScrapeTask(BaseModel):
    """
    Represents a task to scrape a specific geographic area on Google Maps.
    """
    # Payload
    latitude: float
    longitude: float
    zoom: float
    search_phrase: str
    campaign_name: str
    
    # Optional metadata
    radius_miles: Optional[float] = None # approximate radius covered
    tile_id: Optional[str] = None # For Grid Mode: ID of the 0.1 deg tile
    force_refresh: bool = False
    ttl_days: int = 30
    
    # Queue mechanics (Transient)
    ack_token: Optional[str] = Field(None, exclude=True)
    attempts: int = 0

    @property
    def collection(self) -> QueueName:
        return "gm-list"

    def get_shard_id(self) -> str:
        # Shard by latitude prefix for geographic grouping
        return get_shard(str(self.latitude), strategy="geo_tile")

    @property
    def task_id(self) -> str:
        """Unique ID for this scrape task."""
        if self.tile_id:
            return self.tile_id
        return f"{self.latitude}_{self.longitude}_{self.zoom}"

    def get_local_path(self) -> Path:
        """Returns the local pending directory."""
        return paths.campaign(self.campaign_name).queue("gm-list").pending / self.get_shard_id() / self.task_id

    def get_remote_key(self) -> str:
        """Returns the S3 key for this task."""
        return f"campaigns/{self.campaign_name}/queues/gm-list/pending/{self.get_shard_id()}/{self.task_id}/task.json"
    
