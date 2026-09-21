# POLICY: frictionless-data-policy-enforcement
from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path
from typing import ClassVar, Literal, Optional

from pydantic import Field

from .base import QueueMessage
from ....core.ordinant import QueueIdentity, QueueName


class FollowUpTask(QueueMessage):
    """A scheduled follow-up distinct from ToCallTask (queues/to-call) -
    covers non-call follow-through (currently: email), which a single
    callback_at can't represent since more than one can be pending for
    the same company over time (e.g. an email follow-up logged today
    while a later call is also scheduled). ToCallTask's file path is
    keyed by company_slug alone (one pending file per company) - this
    one is keyed by company_slug + id specifically so it doesn't hit
    that same one-per-company ceiling.

    format="email" always carries a template_id - no bespoke/no-template
    path (Mark, 2026-09-16): even a highly personalized follow-up should
    render from a template first, with the personal touch added by
    editing the rendered draft before send (see TargetBatchesView's edit
    action), not generated from scratch per recipient.
    """

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    SCHEMA_UPDATED_AT: ClassVar[str] = "2026-09-16T00:00:00+00:00"

    # Overrides QueueMessage.id's UUID default with a sortable, readable
    # timestamp - matches SendLogEntry/PendingBatchEntry's batch_id convention.
    id: str = Field(default_factory=lambda: datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"))
    scheduled_at: datetime
    format: Literal["call", "email"]
    template_id: Optional[str] = None
    initiative: str = "rta"
    recipient_email: Optional[str] = None

    @property
    def collection(self) -> QueueName:
        return QueueIdentity.FOLLOW_UP

    @property
    def task_id(self) -> str:
        return f"{self.company_slug}__{self.id}"

    def get_local_path(self) -> Path:
        from ....core.paths import paths

        safe_slug = self.company_slug.replace("/", "-").replace("\\", "-")
        return (
            paths.campaign(self.campaign_name).path
            / "queues"
            / "follow-up"
            / "pending"
            / f"{safe_slug}__{self.id}.usv"
        )

    def save(self) -> None:
        path = self.get_local_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_usv(), encoding="utf-8")
        from ....core.paths import paths

        base_queue = paths.campaign(self.campaign_name).path / "queues" / "follow-up"
        self.save_datapackage(base_queue, "follow_up_queue", "**/*.usv")
