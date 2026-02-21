from typing import Optional
from pathlib import Path
from datetime import datetime, UTC
from pydantic import BaseModel, Field
from ....core.paths import paths
from ....core.ordinant import QueueName

class ToCallTask(BaseModel):
    """
    Represents a company ready for human outreach.
    """
    company_slug: str
    campaign_name: str
    priority: int = 1 # 1-5, 5 being highest
    reason: str = "" # e.g. "Has website, has phone, missing email"
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    enqueued_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    
    # Queue mechanics (Transient)
    ack_token: Optional[str] = Field(None, exclude=True)

    @property
    def collection(self) -> QueueName:
        return "to-call"

    def get_shard_id(self) -> str:
        """To-call is currently a flat priority list, no sharding needed."""
        return ""

    @property
    def task_id(self) -> str:
        return self.company_slug

    def get_local_path(self) -> Path:
        """Returns the local pending directory: queues/{campaign}/to-call/pending/{company_slug}"""
        return paths.campaign(self.campaign_name).queue("to-call").pending / self.task_id

    def get_remote_key(self) -> str:
        return f"campaigns/{self.campaign_name}/queues/to-call/pending/{self.task_id}/task.json"
