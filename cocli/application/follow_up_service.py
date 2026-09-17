"""Scheduling and processing of FollowUpTask entries
(queues/follow-up/) - non-call follow-through (currently: email) that
ToCallTask's one-pending-file-per-company path can't represent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Literal, Optional

from ..models.campaigns.queues.follow_up import FollowUpTask


@dataclass
class ProcessFollowUpsResult:
    due: int = 0
    calls_queued: int = 0
    emails_queued: int = 0
    errors: list[str] = field(default_factory=list)


class FollowUpService:
    def __init__(self, campaign_name: str) -> None:
        self.campaign_name = campaign_name

    def add_follow_up(
        self,
        *,
        company_slug: str,
        domain: str,
        scheduled_at: datetime,
        format: Literal["call", "email"],
        template_id: Optional[str] = None,
        initiative: str = "rta",
    ) -> FollowUpTask:
        task = FollowUpTask(
            company_slug=company_slug,
            domain=domain,
            campaign_name=self.campaign_name,
            scheduled_at=scheduled_at,
            format=format,
            template_id=template_id,
            initiative=initiative,
        )
        task.save()
        return task

    def list_pending(self, company_slug: Optional[str] = None) -> list[FollowUpTask]:
        base = self._pending_dir()
        if not base.exists():
            return []
        tasks: list[FollowUpTask] = []
        for p in sorted(base.glob("*.usv")):
            try:
                tasks.append(FollowUpTask.from_usv(p.read_text(encoding="utf-8")))
            except Exception:
                continue
        if company_slug is not None:
            tasks = [t for t in tasks if t.company_slug == company_slug]
        return sorted(tasks, key=lambda t: t.scheduled_at)

    def process_due(self, *, as_of: Optional[datetime] = None) -> ProcessFollowUpsResult:
        """"call" format creates a ToCallTask (folding into the existing,
        working call queue rather than duplicating it). "email" format
        renders the template into a PendingBatchEntry for human review in
        TargetBatchesView - never auto-sent (Mark, 2026-09-16: "that's
        definitely me, not automated send"). Processed rows are removed
        from pending/, same current-state discipline as ToCallTask/
        PendingBatchEntry - a failure leaves the row in place to retry
        next run rather than silently dropping it."""
        as_of = as_of or datetime.now(UTC)
        result = ProcessFollowUpsResult()
        due = [t for t in self.list_pending() if t.scheduled_at <= as_of]
        result.due = len(due)

        for task in due:
            try:
                if task.format == "call":
                    self._queue_call(task)
                    result.calls_queued += 1
                else:
                    self._queue_email(task)
                    result.emails_queued += 1
                task.get_local_path().unlink(missing_ok=True)
            except Exception as exc:
                result.errors.append(f"{task.company_slug}: {exc}")

        return result

    def _pending_dir(self) -> Path:
        from ..core.paths import paths

        return paths.campaign(self.campaign_name).path / "queues" / "follow-up" / "pending"

    def _queue_call(self, task: FollowUpTask) -> None:
        from ..models.campaigns.queues.to_call import ToCallTask

        ToCallTask(
            company_slug=task.company_slug,
            domain=task.domain,
            campaign_name=self.campaign_name,
        ).save()

    def _queue_email(self, task: FollowUpTask) -> None:
        from .personalized_outreach_service import PersonalizedOutreachService
        from ..models.campaigns.indexes.email_pending_batch import PendingBatchEntry

        if not task.template_id:
            raise ValueError("email follow-up has no template_id")

        service = PersonalizedOutreachService(self.campaign_name)
        match = service.find_contact_for_company(task.company_slug)
        if not match:
            raise ValueError(f"no eligible contact found for {task.company_slug}")

        subject, body = service.generate_copy(
            first_name=match.first_name,
            company_name=match.company_name,
            company_slug=task.company_slug,
            template_name=task.template_id,
            initiative=task.initiative,
        )
        match.subject = subject
        match.body = body

        batch_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        entry = PendingBatchEntry(
            batch_id=batch_id,
            template_id=task.template_id,
            company_slug=task.company_slug,
            recipient=match.recipient_email,
            subject=subject,
            body=body,
            initiative=task.initiative,
        )
        service.append_pending_batch_entries([entry])
        # Writes rendered-outreach/<slug>/<template>.md - the file Mark
        # hand-edits before sending (see render_and_save_draft() and
        # entry_to_match()), not just an audit record.
        service.render_and_save_draft(match, template_id=task.template_id, initiative=task.initiative)
