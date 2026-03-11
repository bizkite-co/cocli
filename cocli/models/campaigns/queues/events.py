# POLICY: frictionless-data-policy-enforcement
from typing import Optional, Literal
from pathlib import Path
from pydantic import Field
from ....core.paths import paths
from ....core.ordinant import QueueName, QueueIdentity
from ...base import BaseUsvModel

class EventScrapeTask(BaseUsvModel):
    """
    Represents a task to scrape events from a specific source or search query.
    """
    url: Optional[str] = None
    search_phrase: Optional[str] = None
    host_name: str
    host_slug: str
    campaign_name: str = "fullertonian"
    scraper_type: Literal["eventbrite", "fullerton-observer", "fullerton-library", "web-search", "generic-calendar"] = "generic-calendar"
    is_active: bool = Field(default=True, description="Whether this source is currently active for scraping")
    
    # Queue mechanics (Transient)
    ack_token: Optional[str] = Field(None, exclude=True)
    attempts: int = 0

    @property
    def collection(self) -> QueueName:
        return QueueIdentity.EVENTS

    def get_shard_id(self) -> str:
        """Shard by host_slug (first letter)."""
        return self.host_slug[0] if self.host_slug else "_"

    def get_local_path(self) -> Path:
        """
        Returns the canonical local path in the events pending queue.
        Path: queues/events/pending/{shard}/{host_slug}/
        """
        return paths.campaign(self.campaign_name).queue(QueueIdentity.EVENTS).pending / self.get_shard_id() / self.host_slug

    def get_remote_key(self) -> str:
        """Returns the S3 key for this task."""
        return f"campaigns/{self.campaign_name}/queues/events/pending/{self.get_shard_id()}/{self.host_slug}/task.json"

    def save(self) -> Path:
        """Saves the task to its local directory."""
        path = self.get_local_path()
        path.mkdir(parents=True, exist_ok=True)
        task_file = path / "task.json"
        task_file.write_text(self.model_dump_json(indent=2))
        return task_file
