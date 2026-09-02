# POLICY: frictionless-data-policy-enforcement
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from .base import QueueMessage
from ....core.ordinant import QueueIdentity, QueueName


class ToCallHighValueTask(QueueMessage):
    """Speculative: this prospect may produce high-value transactions.

    Stays on to-call. This queue is a filter/review pile, not a yank.
    """

    SCHEMA_UPDATED_AT: ClassVar[str] = "2026-09-02T00:00:00+00:00"

    reason: str = "high-value"

    @property
    def collection(self) -> QueueName:
        return QueueIdentity.TO_CALL_HIGH_VALUE

    @property
    def task_id(self) -> str:
        return self.company_slug

    def get_local_path(self) -> Path:
        from ....core.paths import paths

        safe_slug = self.company_slug.replace("/", "-").replace("\\", "-")
        return (
            paths.campaign(self.campaign_name).path
            / "queues"
            / "to-call-high-value"
            / "pending"
            / f"{safe_slug}.usv"
        )

    def save(self) -> None:
        path = self.get_local_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_usv(), encoding="utf-8")
        from ....core.paths import paths

        base_queue = (
            paths.campaign(self.campaign_name).path / "queues" / "to-call-high-value"
        )
        self.save_datapackage(base_queue, "to_call_high_value_queue", "**/*.usv")
