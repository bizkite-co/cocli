"""Browse, edit, and dispatch pending follow-up queue items.

Source: campaigns/<campaign>/queues/follow-up/pending/*.usv
Each FollowUpTask can be:
  - Prepared (p): renders the template into a PendingBatchEntry so it
    appears in Batch Email Drafts for final review/send.
  - Edited (e): opens the inline EditPendingEntryModal to tweak the
    subject/body *before* freezing.  We render a preview on-the-fly
    (without saving to pending.usv) and let the user adjust it, then
    re-freeze with the edited copy.
  - Deleted (d): removes the .usv file without sending.
  - Refreshed (ctrl+r).

Editing strategy: render → show EditPendingEntryModal → if saved,
freeze the edited copy into email-pending-batch/pending.usv and delete
this queue row.  Uses existing PersonalizedOutreachService and
EditPendingEntryModal so no new send path is needed.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast, TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import CocliApp
    from cocli.models.campaigns.queues.follow_up import FollowUpTask

from textual import events, on
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Label, ListItem, ListView, Static

from .master_detail import MasterDetailView

logger = logging.getLogger(__name__)


class FollowUpQueueListItem(ListItem):
    def __init__(self, task: "FollowUpTask") -> None:
        super().__init__()
        self.follow_up = task

    def compose(self) -> Any:
        t = self.follow_up
        due_str = t.scheduled_at.strftime("%Y-%m-%d")
        fmt_icon = "✉" if t.format == "email" else "📞"
        tpl = f" [{t.template_id}]" if t.template_id else ""
        yield Label(f"{fmt_icon} {due_str}  {t.company_slug}{tpl}")


class FollowUpQueuePreview(VerticalScroll):
    def compose(self) -> Any:
        yield Label(
            "Select an item to preview.\n\n"
            "p: Prepare (render → Batch Drafts)  "
            "e: Edit then prepare  "
            "d: Delete",
            id="fu-preview-empty",
        )
        yield Static("", id="fu-preview-body")

    def update_preview(self, task: "FollowUpTask | None") -> None:
        empty = self.query_one("#fu-preview-empty", Label)
        body = self.query_one("#fu-preview-body", Static)
        if task is None:
            empty.display = True
            body.update("")
            return
        empty.display = False
        lines = [
            f"[bold]Company:[/bold]   {task.company_slug}",
            f"[bold]Domain:[/bold]    {task.domain}",
            f"[bold]Format:[/bold]    {task.format}",
            f"[bold]Template:[/bold]  {task.template_id or '(none)'}",
            f"[bold]Scheduled:[/bold] {task.scheduled_at.strftime('%Y-%m-%d %H:%M UTC')}",
            f"[bold]Initiative:[/bold]{task.initiative}",
            "",
            "[dim]p: Prepare selected[/dim]",
            "[dim]P: Prepare all due follow-ups[/dim]",
            "[dim]e: Edit rendered copy then prepare[/dim]",
            "[dim]d: Delete this follow-up[/dim]",
        ]
        body.update("\n".join(lines))


class FollowUpQueueView(MasterDetailView):
    """Master: pending follow-up queue items (queues/follow-up/pending/).
    Detail: task metadata + action hints.  Actions render into
    email-pending-batch/pending.usv (Batch Email Drafts) rather than
    auto-sending."""

    BINDINGS = [
        Binding("p", "prepare_selected", "Prepare Selected", show=True),
        Binding("P", "prepare_all_due", "Prepare All Due", show=True),
        Binding("e", "edit_and_prepare", "Edit & Prepare", show=True),
        Binding("d", "delete_task", "Delete", show=True),
        Binding("ctrl+r", "refresh", "Refresh", show=True),
    ]

    def __init__(self, **kwargs: Any) -> None:
        self.task_list = ListView(id="fu-queue-list")
        self.task_preview = FollowUpQueuePreview(id="fu-queue-preview")
        super().__init__(
            master=self.task_list, detail=self.task_preview, master_width=45, **kwargs
        )

    async def on_mount(self) -> None:
        self.refresh_tasks()

    # ------------------------------------------------------------------
    # List population
    # ------------------------------------------------------------------

    def refresh_tasks(self) -> None:
        from cocli.application.follow_up_service import FollowUpService

        app = cast("CocliApp", self.app)
        tasks = FollowUpService(app.services.campaign_name).list_pending()
        self.task_list.clear()
        for task in tasks:
            self.task_list.append(FollowUpQueueListItem(task))
        if tasks:
            self.task_list.index = 0
            self.task_preview.update_preview(tasks[0])
        else:
            self.task_preview.update_preview(None)

    # ------------------------------------------------------------------
    # Selection / highlight
    # ------------------------------------------------------------------

    @on(ListView.Selected)
    def on_task_selected(self, message: ListView.Selected) -> None:
        if isinstance(message.item, FollowUpQueueListItem):
            self.task_preview.update_preview(message.item.follow_up)

    @on(ListView.Highlighted, "#fu-queue-list")
    def on_task_highlighted(self, message: ListView.Highlighted) -> None:
        if isinstance(message.item, FollowUpQueueListItem):
            self.task_preview.update_preview(message.item.follow_up)

    def _highlighted_task(self) -> "FollowUpTask | None":
        item = self.task_list.highlighted_child
        if isinstance(item, FollowUpQueueListItem):
            return item.follow_up
        return None

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def on_key(self, event: events.Key) -> None:
        if event.key == "j":
            self.task_list.action_cursor_down()
            event.prevent_default()
        elif event.key == "k":
            self.task_list.action_cursor_up()
            event.prevent_default()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_refresh(self) -> None:
        self.refresh_tasks()

    def action_prepare(self) -> None:
        self.action_prepare_selected()

    def action_prepare_selected(self) -> None:
        task = self._highlighted_task()
        if task is None:
            self.app.notify("No follow-up selected.", severity="warning")
            return
        self.run_worker(self._prepare_single_flow(task), exclusive=True)

    def action_prepare_all_due(self) -> None:
        self.run_worker(self._prepare_all_flow(), exclusive=True)

    def action_edit_and_prepare(self) -> None:
        task = self._highlighted_task()
        if task is None:
            return
        self.run_worker(self._edit_and_prepare_flow(task), exclusive=True)

    def action_delete_task(self) -> None:
        task = self._highlighted_task()
        if task is None:
            return
        self.run_worker(self._delete_flow(task), exclusive=True)

    # ------------------------------------------------------------------
    # Workers
    # ------------------------------------------------------------------

    async def _prepare_single_flow(self, task: "FollowUpTask") -> None:
        """Render selected follow-up → PendingBatchEntry (Batch Email Drafts)."""
        from cocli.application.follow_up_service import FollowUpService

        app = cast("CocliApp", self.app)
        try:
            await asyncio.to_thread(
                lambda: FollowUpService(app.services.campaign_name).process_task(task)
            )
        except Exception as exc:
            self.app.notify(f"Prepare failed for {task.company_slug}: {exc}", severity="error")
            return

        fmt_desc = "email draft" if task.format == "email" else "call"
        self.app.notify(f"Prepared {fmt_desc} for {task.company_slug} → Batch Email Drafts")
        self.refresh_tasks()

    async def _prepare_all_flow(self) -> None:
        """Render all due follow-ups → PendingBatchEntry rows (Batch Email Drafts)."""
        from cocli.application.follow_up_service import FollowUpService

        app = cast("CocliApp", self.app)
        try:
            result = await asyncio.to_thread(
                lambda: FollowUpService(app.services.campaign_name).process_due()
            )
        except Exception as exc:
            self.app.notify(f"Prepare failed: {exc}", severity="error")
            return

        if result.errors:
            self.app.notify(
                f"Prepared {result.emails_queued} email(s); "
                f"{len(result.errors)} error(s): {result.errors[0]}",
                severity="warning",
            )
        else:
            self.app.notify(
                f"Prepared {result.emails_queued} email / "
                f"{result.calls_queued} call follow-up(s) → Batch Email Drafts"
            )
        self.refresh_tasks()

    async def _edit_and_prepare_flow(self, task: "FollowUpTask") -> None:
        """Render template on-the-fly, open editor, then freeze the edited copy."""
        from .edit_pending_entry_modal import EditPendingEntryModal
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService
        from cocli.models.campaigns.indexes.email_pending_batch import PendingBatchEntry

        if task.format != "email":
            self.app.notify(
                "Edit & Prepare only applies to email follow-ups.", severity="warning"
            )
            return
        if not task.template_id:
            self.app.notify("No template_id on this task.", severity="error")
            return

        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        service = PersonalizedOutreachService(campaign)

        # Render the template without freezing yet.
        try:
            match = await asyncio.to_thread(
                service.find_contact_for_company, task.company_slug
            )
        except Exception as exc:
            self.app.notify(f"Could not find contact: {exc}", severity="error")
            return

        if match is None:
            self.app.notify(
                f"No eligible contact found for {task.company_slug}", severity="error"
            )
            return

        try:
            subject, body = await asyncio.to_thread(
                service.generate_copy,
                first_name=match.first_name,
                company_name=match.company_name,
                company_slug=task.company_slug,
                template_name=task.template_id,
                initiative=task.initiative,
            )
        except Exception as exc:
            self.app.notify(f"Template render failed: {exc}", severity="error")
            return

        # Let the user edit.
        result = await self.app.push_screen_wait(
            EditPendingEntryModal(subject, body)
        )
        if result is None:
            return  # cancelled — queue file stays untouched
        edited_subject, edited_body = result

        # Freeze the edited copy into pending.usv.
        from datetime import datetime, UTC

        batch_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        entry = PendingBatchEntry(
            batch_id=batch_id,
            template_id=task.template_id,
            company_slug=task.company_slug,
            recipient=match.recipient_email,
            subject=edited_subject,
            body=edited_body,
            initiative=task.initiative,
        )
        try:
            await asyncio.to_thread(service.append_pending_batch_entries, [entry])
            await asyncio.to_thread(
                service.render_and_save_draft,
                match,
                template_id=task.template_id,
                initiative=task.initiative,
            )
        except Exception as exc:
            self.app.notify(f"Could not save draft: {exc}", severity="error")
            return

        # Remove the follow-up queue file.
        try:
            task.get_local_path().unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("Could not remove follow-up queue file: %s", exc)

        self.app.notify(
            f"Saved edited draft for {task.company_slug} → Batch Email Drafts"
        )
        self.refresh_tasks()

    async def _delete_flow(self, task: "FollowUpTask") -> None:
        from .confirm_screen import ConfirmScreen

        confirmed = await self.app.push_screen_wait(
            ConfirmScreen(
                f"Delete follow-up for {task.company_slug} "
                f"(scheduled {task.scheduled_at:%Y-%m-%d})?"
            )
        )
        if not confirmed:
            return
        try:
            task.get_local_path().unlink(missing_ok=True)
        except Exception as exc:
            self.app.notify(f"Delete failed: {exc}", severity="error")
            return
        self.app.notify(f"Deleted follow-up for {task.company_slug}")
        self.refresh_tasks()
