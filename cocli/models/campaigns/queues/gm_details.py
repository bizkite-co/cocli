from pydantic import BaseModel, Field
from typing import Optional
from pathlib import Path
from ....core.paths import paths
from ....core.ordinant import QueueName
from ....core.sharding import get_place_id_shard


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
    gmb_url: Optional[str] = None
    discovery_phrase: Optional[str] = None
    discovery_tile_id: Optional[str] = None

    # Queue mechanics (Transient)
    ack_token: Optional[str] = Field(default=None, exclude=True)
    attempts: int = 0

    @property
    def collection(self) -> QueueName:
        from ....core.ordinant import QueueIdentity
        return QueueIdentity.GM_DETAILS

    def get_shard_id(self) -> str:
        # Path authority: same as FSQ / get_place_id_shard (raw alphabet, P14)
        return get_place_id_shard(self.place_id)

    def get_local_path(self) -> Path:
        """Local pending dir: queues/.../gm-details/pending/{shard}/{place_id}"""
        return (
            paths.campaign(self.campaign_name).queue("gm-details").pending
            / self.get_shard_id()
            / self.place_id
        )

    def get_remote_key(self) -> str:
        """S3 task key — same shape as FilesystemQueue._get_s3_task_key."""
        return (
            f"campaigns/{self.campaign_name}/queues/gm-details/pending/"
            f"{self.get_shard_id()}/{self.place_id}/task.json"
        )
