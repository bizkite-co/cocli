from typing import Optional, ClassVar
from pathlib import Path
from pydantic import Field
from ....core.paths import paths
from ....core.ordinant import QueueName
from ...base import BaseUsvModel
from ....core.geo_types import LatScale1, LonScale1


class ScrapeTask(BaseUsvModel):
    """
    Represents a task to scrape a specific geographic area on Google Maps.
    """

    # Payload
    latitude: LatScale1
    longitude: LonScale1
    zoom: float
    search_phrase: str
    campaign_name: str

    # Optional metadata
    radius_miles: Optional[float] = None  # approximate radius covered
    tile_id: Optional[str] = None  # For Grid Mode: ID of the 0.1 deg tile
    force_refresh: bool = False
    ttl_days: int = 30

    # Queue mechanics (Transient)
    ack_token: Optional[str] = Field(None, exclude=True)
    attempts: int = 0
    result_count: Optional[int] = None  # Capture discovery count for receipt

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    @property
    def collection(self) -> QueueName:
        return "gm-list"

    def get_shard_id(self) -> str:
        """Standardized Geo Shard (first digit of latitude)."""
        from ....core.sharding import get_geo_shard

        return get_geo_shard(float(self.latitude))

    def get_local_path(self) -> Path:
        """
        Returns the OMAP-compliant local directory for the task lease.
        Path: queues/gm-list/pending/{shard}/{lat}/{lon}/{phrase}.usv/
        """
        from ....core.text_utils import slugify
        from ....core.geo_types import LatScale1, LonScale1

        shard = self.get_shard_id()
        lat = (
            self.latitude
            if isinstance(self.latitude, LatScale1)
            else LatScale1(float(self.latitude))
        )
        lon = (
            self.longitude
            if isinstance(self.longitude, LonScale1)
            else LonScale1(float(self.longitude))
        )
        phrase = slugify(self.search_phrase)

        return (
            paths.campaign(self.campaign_name).queue("gm-list").pending
            / shard
            / str(lat)
            / str(lon)
            / f"{phrase}.usv"
        )

    def get_remote_key(self) -> str:
        """Returns the OMAP-compliant S3 key for this task."""
        from ....core.text_utils import slugify
        from ....core.geo_types import LatScale1, LonScale1

        shard = self.get_shard_id()
        lat = (
            self.latitude
            if isinstance(self.latitude, LatScale1)
            else LatScale1(float(self.latitude))
        )
        lon = (
            self.longitude
            if isinstance(self.longitude, LonScale1)
            else LonScale1(float(self.longitude))
        )
        phrase = slugify(self.search_phrase)

        return f"campaigns/{self.campaign_name}/queues/gm-list/pending/{shard}/{lat}/{lon}/{phrase}.usv/task.json"
