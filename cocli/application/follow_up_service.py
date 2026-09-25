"""Scheduling and processing of FollowUpTask entries
(queues/follow-up/) - non-call follow-through (currently: email) that
ToCallTask's one-pending-file-per-company path can't represent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Literal, Optional

from ..models.campaigns.queues.follow_up import FollowUpTask


@dataclass
class ProcessFollowUpsResult:
    due: int = 0
    calls_queued: int = 0
    emails_queued: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class EnqueueInitiativeResult:
    initiative: str
    enqueued: int = 0
    rendered: int = 0
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
        recipient_email: Optional[str] = None,
    ) -> FollowUpTask:
        task = FollowUpTask(
            company_slug=company_slug,
            domain=domain,
            campaign_name=self.campaign_name,
            scheduled_at=scheduled_at,
            format=format,
            template_id=template_id,
            initiative=initiative,
            recipient_email=recipient_email,
        )
        task.save()
        return task

    def enqueue_by_tag(
        self,
        tag: str,
        *,
        template_id: str,
        initiative: str = "rta",
        format: Literal["call", "email"] = "email",
        scheduled_at: Optional[datetime] = None,
    ) -> list[FollowUpTask]:
        """Enqueue follow-up tasks for all companies in this campaign that have `tag`."""
        from .personalized_outreach_service import PersonalizedOutreachService
        from ..models.companies.company import Company
        from ..core.paths import paths

        outreach = PersonalizedOutreachService(self.campaign_name)
        scheduled_at = scheduled_at or datetime.now(UTC)
        tasks: list[FollowUpTask] = []

        companies_dir = paths.companies.ensure()
        for idx_file in sorted(companies_dir.glob("*/_index.md")):
            slug = idx_file.parent.name
            company = Company.get(slug)
            if not company or not company.belongs_to_campaign(self.campaign_name):
                continue
            if tag not in (company.tags or []):
                continue

            match = outreach.find_contact_for_company(slug)
            recipient_email = match.recipient_email if match else (str(company.email) if company.email else None)

            task = self.add_follow_up(
                company_slug=slug,
                domain=company.domain or "unknown",
                scheduled_at=scheduled_at,
                format=format,
                template_id=template_id,
                initiative=initiative,
                recipient_email=recipient_email,
            )
            tasks.append(task)
        return tasks

    def enqueue_initiative(
        self,
        initiative_name: str,
        *,
        template_id: Optional[str] = None,
        render: bool = True,
        dry_run: bool = False,
        scheduled_at: Optional[datetime] = None,
    ) -> EnqueueInitiativeResult:
        """Enqueue follow-up tasks for all companies matching the initiative's declarative manifest."""
        from .personalized_outreach_service import PersonalizedOutreachService
        from ..models.campaigns.initiative import InitiativeManifest
        from ..models.companies.company import Company
        from ..core.paths import paths

        manifest = InitiativeManifest.find(self.campaign_name, initiative_name)
        if not manifest:
            raise ValueError(
                f"No initiative.yaml found for initiative '{initiative_name}' in campaign '{self.campaign_name}'"
            )

        active_template = template_id or manifest.default_template
        active_format = manifest.outreach.format
        scheduled_at = scheduled_at or (datetime.now(UTC) + timedelta(days=manifest.outreach.follow_up_delay_days))

        outreach = PersonalizedOutreachService(self.campaign_name)
        companies_dir = paths.companies.ensure()
        matching_companies: list[Company] = []

        cache_path = (
            paths.campaign(self.campaign_name).path
            / "indexes"
            / "company_cache"
            / "company_cache.usv"
        )
        criteria = manifest.target_criteria

        if cache_path.exists():
            for line in cache_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                parts = line.split("\x1f")
                if len(parts) < 9:
                    continue
                slug = parts[0]
                raw_tags = parts[8]
                tags_list = [t.strip().lower() for t in raw_tags.replace(",", ";").split(";") if t.strip()]

                if criteria.tags:
                    if not all(tag.lower() in tags_list for tag in criteria.tags):
                        continue
                if criteria.excluded_tags:
                    if any(tag.lower() in tags_list for tag in criteria.excluded_tags):
                        continue
                if criteria.company_type:
                    if criteria.company_type.lower() not in tags_list:
                        continue

                co = Company.get(slug)
                if co:
                    matching_companies.append(co)
        else:
            for idx_file in sorted(companies_dir.glob("*/_index.md")):
                slug = idx_file.parent.name
                company = Company.get(slug)
                if not company or not company.belongs_to_campaign(self.campaign_name):
                    continue

                company_tags = [t.lower() for t in (company.tags or [])]
                if criteria.tags:
                    if not all(tag.lower() in company_tags for tag in criteria.tags):
                        continue
                if criteria.excluded_tags:
                    if any(tag.lower() in company_tags for tag in criteria.excluded_tags):
                        continue
                if criteria.company_type:
                    if criteria.company_type.lower() not in company_tags:
                        continue

                matching_companies.append(company)

        if dry_run:
            return EnqueueInitiativeResult(
                initiative=initiative_name,
                enqueued=len(matching_companies),
                rendered=0,
            )

        tasks: list[FollowUpTask] = []
        for company in matching_companies:
            match = outreach.find_contact_for_company(company.slug)
            recipient_email = match.recipient_email if match else (str(company.email) if company.email else None)

            task = self.add_follow_up(
                company_slug=company.slug,
                domain=company.domain or "unknown",
                scheduled_at=scheduled_at,
                format=active_format,
                template_id=active_template,
                initiative=initiative_name,
                recipient_email=recipient_email,
            )
            tasks.append(task)

        rendered_count = 0
        errors: list[str] = []
        if render:
            process_res = self.process_due(as_of=scheduled_at)
            rendered_count = process_res.emails_queued if active_format == "email" else process_res.calls_queued
            errors.extend(process_res.errors)

        return EnqueueInitiativeResult(
            initiative=initiative_name,
            enqueued=len(tasks),
            rendered=rendered_count,
            errors=errors,
        )

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
                self.process_task(task)
                if task.format == "call":
                    result.calls_queued += 1
                else:
                    result.emails_queued += 1
            except Exception as exc:
                result.errors.append(f"{task.company_slug}: {exc}")

        return result

    def process_task(self, task: FollowUpTask) -> None:
        """Process a single FollowUpTask (call or email), queueing it and removing the pending queue file."""
        if task.format == "call":
            self._queue_call(task)
        else:
            self._queue_email(task)
        task.get_local_path().unlink(missing_ok=True)

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
        match = service.find_contact_for_company(
            task.company_slug, recipient_email=getattr(task, "recipient_email", None)
        )
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
        service.upsert_pending_batch_entries([entry])
        # Writes rendered-outreach/<slug>/<template>.md - the file Mark
        # hand-edits before sending (see render_and_save_draft() and
        # entry_to_match()), not just an audit record.
        service.render_and_save_draft(match, template_id=task.template_id, initiative=task.initiative)
