from pydantic import BaseModel, Field
from typing import Optional
from pathlib import Path
from ..core.paths import paths
from ..core.ordinant import QueueName, get_shard

class GmItemTask(BaseModel):
    """
    Represents a task to scrape details for a specific Google Maps item (Place ID).
    This is the bridge between gm-list and gm-details.
    """
    place_id: str
    campaign_name: str
    name: str = ""
    company_slug: str = ""
    force_refresh: bool = False
    discovery_phrase: Optional[str] = None
    discovery_tile_id: Optional[str] = None
    
    # Queue mechanics (Transient)
    ack_token: Optional[str] = Field(default=None, exclude=True)
    attempts: int = 0

    @property
    def collection(self) -> QueueName:
        return "gm-details"

    def get_shard_id(self) -> str:
        return get_shard(self.place_id, strategy="place_id")

    def get_local_path(self) -> Path:
        """Returns the local pending directory."""
        return paths.campaign(self.campaign_name).queue("gm-details").pending / self.get_shard_id() / self.place_id

    def get_remote_key(self) -> str:
        """Returns the S3 key for this task."""
        return f"campaigns/{self.campaign_name}/queues/gm-details/pending/{self.get_shard_id()}/{self.place_id}/task.json"
