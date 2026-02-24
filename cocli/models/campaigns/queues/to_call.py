# POLICY: frictionless-data-policy-enforcement
from pathlib import Path
from datetime import datetime
from typing import Optional
from .base import QueueMessage
from ....core.ordinant import QueueName

class ToCallTask(QueueMessage):
    """
    Represents a company to be contacted.
    Supports scheduling via callback_at.
    """
    priority: int = 1
    callback_at: Optional[datetime] = None
    
    @property
    def collection(self) -> QueueName:
        return "to-call"

    @property
    def task_id(self) -> str:
        return self.company_slug

    def get_local_path(self) -> Path:
        """
        Returns the local path for the task file.
        Active: queues/{campaign}/to-call/pending/{company_slug}.usv
        Scheduled: queues/{campaign}/to-call/scheduled/{YYYY}/{MM}/{DD}/{YYYYMMDD_HHMMSS}_{slug}.usv
        """
        # FDPE: Local import to ensure we respect current re-rooted paths authority
        from ....core.paths import paths
        base_queue = paths.campaign(self.campaign_name).path / "queues" / "to-call"
        
        if self.callback_at:
            # Date-sharded: scheduled/YYYY/MM/DD/TIMESTAMP_slug.usv
            date_dir = self.callback_at.strftime("%Y/%m/%d")
            ts_prefix = self.callback_at.strftime("%Y%m%d_%H%M%S")
            return base_queue / "scheduled" / date_dir / f"{ts_prefix}_{self.company_slug}.usv"
        else:
            # Active: pending/slug.usv
            return base_queue / "pending" / f"{self.company_slug}.usv"

    def save(self) -> None:
        """Saves the task to its sharded local path in USV format."""
        path = self.get_local_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_usv(), encoding="utf-8")
        
        # Ensure datapackage exists in the collection root
        # FDPE: Local import to ensure we respect current re-rooted paths authority
        from ....core.paths import paths
        base_queue = paths.campaign(self.campaign_name).path / "queues" / "to-call"
        self.save_datapackage(base_queue, "to_call_queue", "pending/*.usv")
