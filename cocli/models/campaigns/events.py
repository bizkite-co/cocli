# POLICY: frictionless-data-policy-enforcement
from datetime import datetime
from typing import Optional, List
from pydantic import Field
from pathlib import Path
import yaml
from ..base import BaseUsvModel
from ...core.paths import paths
from ...core.ordinant import QueueIdentity, QueueName
import logging

logger = logging.getLogger(__name__)

class Event(BaseUsvModel):
    """
    Standard model for Fullertonian community events.
    Stored as directories with README.md (YAML frontmatter + Markdown body).
    Allows for attaching images/assets in the same folder.
    """
    # Authoritative Sequence for USV
    start_time: datetime = Field(..., description="ISO datetime of the event")
    host_slug: str = Field(..., description="Slug of the hosting organization/venue")
    event_slug: str = Field(..., description="Slug of the event name")
    name: str = Field(..., description="Full human-readable event name")
    host_name: str = Field(..., description="Full human-readable host name")
    
    location: Optional[str] = None
    fee: Optional[str] = "Free"
    description: Optional[str] = None
    url: Optional[str] = None
    image_url: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    
    # Curation Flags
    is_excluded: bool = Field(default=False, description="Manually marked for exclusion")
    is_highlighted: bool = Field(default=False, description="Manually marked for highlight")
    
    # Metadata
    campaign_name: str = "fullertonian"
    source_url: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now())

    @property
    def collection(self) -> QueueName:
        return QueueIdentity.EVENTS

    def get_shard_id(self) -> str:
        """Returns the shard ID based on event start time (YYYYMM)."""
        return self.start_time.strftime("%Y%m")

    def get_local_path(self) -> Path:
        """Returns the canonical local path in the events WAL."""
        return paths.campaign(self.campaign_name).queue(QueueIdentity.EVENTS).wal / self.get_shard_id() / self.get_event_dir_name()

    def get_remote_key(self) -> str:
        """Returns the S3 key for this event."""
        return f"campaigns/{self.campaign_name}/queues/events/wal/{self.get_shard_id()}/{self.get_event_dir_name()}/README.md"
    
    def get_event_dir_name(self) -> str:
        """
        Generates the standard directory name:
        ISO_DATETIME_host-slug_event-slug
        """
        ts = self.start_time.strftime("%Y%m%dT%H%M%S")
        return f"{ts}_{self.host_slug}_{self.event_slug}"

    def download_assets(self) -> None:
        """
        Downloads the event image if an image_url is provided.
        Saves it as 'hero.jpg' (or appropriate extension) in the event directory.
        """
        if not self.image_url:
            return
            
        import httpx
        event_dir = self.get_local_path()
        event_dir.mkdir(parents=True, exist_ok=True)
        
        # Determine extension
        ext = self.image_url.split('.')[-1].split('?')[0].lower()
        if ext not in ['jpg', 'jpeg', 'png', 'webp', 'gif']:
            ext = 'jpg'
            
        asset_path = event_dir / f"hero.{ext}"
        
        try:
            with httpx.Client(follow_redirects=True) as client:
                resp = client.get(self.image_url)
                resp.raise_for_status()
                asset_path.write_bytes(resp.content)
                logger.info(f"Downloaded asset: {asset_path}")
        except Exception as e:
            logger.error(f"Failed to download asset from {self.image_url}: {e}")

    def save(self) -> Path:
        """
        Saves the event to its canonical location as a directory with a README.md file.
        """
        event_dir = self.get_local_path()
        event_dir.mkdir(parents=True, exist_ok=True)
        
        # Download assets if they haven't been downloaded yet
        # Only download if not excluded
        if not self.is_excluded:
            self.download_assets()
        
        readme_path = event_dir / "README.md"
        
        # Prepare frontmatter
        data = self.model_dump(mode="json", exclude_none=True)
        description = data.pop("description", "")
        
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write("---\n")
            yaml.safe_dump(data, f, sort_keys=False)
            f.write("---\n")
            if description:
                f.write(f"\n{description}\n")
                
        return event_dir

    def save_to_wal(self, wal_dir: Path) -> Path:
        """
        Legacy/Manual save method. Prefer .save() for canonical pathing.
        """
        return self.save()
