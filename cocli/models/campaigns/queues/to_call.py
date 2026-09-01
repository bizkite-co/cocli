# POLICY: frictionless-data-policy-enforcement
from pathlib import Path
from datetime import datetime
from typing import Optional, ClassVar
from .base import QueueMessage
from ....core.ordinant import QueueName


class ToCallTask(QueueMessage):
    """
    Represents a company to be contacted.
    Supports scheduling via callback_at.
    """

    SCHEMA_UPDATED_AT: ClassVar[str] = "2026-06-25T15:09:30+00:00"

    priority: int = 1
    callback_at: Optional[datetime] = None


    @property
    def collection(self) -> QueueName:
        from ....core.ordinant import QueueIdentity
        return QueueIdentity.TO_CALL


    @property
    def task_id(self) -> str:
        return self.company_slug

    def get_local_path(self) -> Path:
        """
        Returns the local path for the task file:
        queues/{campaign}/to-call/pending/{company_slug}.usv

        Mark, 2026-09-01: previously a task with callback_at set went to a
        separate date-sharded scheduled/ directory - but nothing ever read
        that directory back, so a scheduled follow-up silently vanished
        once its date arrived. Everything now lives in pending/; callback_at
        is the due date, checked by whatever reads the queue (see
        search_service.py's items_to_call population) rather than encoded
        in the path.
        """
        # FDPE: Local import to ensure we respect current re-rooted paths authority
        from ....core.paths import paths

        base_queue = paths.campaign(self.campaign_name).path / "queues" / "to-call"

        # Sanitize company_slug to avoid path issues (e.g., "/" in "24/7" becomes subdirectory)
        safe_slug = self.company_slug.replace("/", "-").replace("\\", "-")

        return base_queue / "pending" / f"{safe_slug}.usv"

    def save(self) -> None:
        """Saves the task to its sharded local path in USV format."""
        path = self.get_local_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_usv(), encoding="utf-8")

        # Ensure datapackage exists in the collection root
        # FDPE: Local import to ensure we respect current re-rooted paths authority
        from ....core.paths import paths

        base_queue = paths.campaign(self.campaign_name).path / "queues" / "to-call"
        self.save_datapackage(base_queue, "to_call_queue", "**/*.usv")

