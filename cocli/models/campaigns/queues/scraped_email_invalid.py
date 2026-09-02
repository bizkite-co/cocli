# POLICY: frictionless-data-policy-enforcement
from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Optional

from .base import QueueMessage
from ....core.ordinant import QueueIdentity, QueueName


class ScrapedEmailInvalidTask(QueueMessage):
    """A scraped address that is not a real inbox (placeholder or ROT13).

    Review pile for refining website email extraction against raw witness HTML.
    """

    SCHEMA_UPDATED_AT: ClassVar[str] = "2026-09-02T00:00:00+00:00"

    email: str
    reason: str
    witness_relpath: str = ""
    context_snippet: str = ""
    extracted_from: str = "html"

    @property
    def collection(self) -> QueueName:
        return QueueIdentity.SCRAPED_EMAIL_INVALID

    @property
    def task_id(self) -> str:
        safe_email = self.email.replace("@", "_at_").replace(".", "_").replace("/", "-")
        return f"{self.company_slug}__{safe_email}"

    def get_local_path(self) -> Path:
        from ....core.paths import paths

        return (
            paths.campaign(self.campaign_name).path
            / "queues"
            / "scraped-email-invalid"
            / "pending"
            / f"{self.task_id}.usv"
        )

    def save(self) -> None:
        path = self.get_local_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_usv(), encoding="utf-8")
        from ....core.paths import paths

        base_queue = (
            paths.campaign(self.campaign_name).path / "queues" / "scraped-email-invalid"
        )
        self.save_datapackage(base_queue, "scraped_email_invalid_queue", "**/*.usv")


def enqueue_scraped_email_invalid(
    *,
    campaign_name: Optional[str],
    company_slug: str,
    domain: str,
    email: str,
    reason: str,
    witness_relpath: str = "",
    context_snippet: str = "",
    extracted_from: str = "html",
) -> Optional[Path]:
    if not campaign_name:
        return None
    task = ScrapedEmailInvalidTask(
        company_slug=company_slug or "unknown",
        domain=domain or "unknown",
        campaign_name=campaign_name,
        email=email,
        reason=reason,
        witness_relpath=witness_relpath,
        context_snippet=context_snippet[:500],
        extracted_from=extracted_from,
        ack_token=None,
    )
    task.save()
    return task.get_local_path()
