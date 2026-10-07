"""Browse, edit, and dispatch every outbound draft in one place: both
not-yet-rendered scheduled follow-ups (queues/follow-up/pending/) and
already-rendered batch drafts (email-pending-batch/pending.usv) - Mark,
2026-10-07: "combine 'Follow-up Drafts' and 'Batch Email Drafts' into a
single 'Draft Messages'".

Same key, different behavior depending on what's selected ("dispatch by
row type" - Mark confirmed this over dropping either capability):
  p  - on a follow-up row: prepare just this one (renders it into a
       batch draft below). On a batch-draft row: already prepared, no-op.
  P  - always: prepare every due follow-up campaign-wide, regardless of
       what's selected (unifies FollowUpQueueView's old "P" and
       TargetBatchesView's old "p", which meant the same thing).
  e  - on a follow-up row: render on-the-fly, let you edit, then freeze
       into a batch draft. On a batch-draft row: edit the already-
       rendered draft in place.
  d  - on a follow-up row: delete the scheduled follow-up. On a
       batch-draft row: discard its whole batch (unchanged from before -
       a batch can have more than one recipient).
  v  - on a batch-draft row: toggle rendered-HTML vs raw-markdown
       preview. On a follow-up row: no-op (nothing rendered yet).
  o  - on a batch-draft row: open the rendered HTML preview in a
       browser. On a follow-up row: no-op.
  s  - on a batch-draft row: send that row's batch. On a follow-up row:
       no-op (prepare it first).
  S  - always: send every pending batch.
  n  - always: start a new ad-hoc batch.
  ctrl+r - always: refresh both follow-ups and batch drafts.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast, TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import CocliApp
    from cocli.models.campaigns.queues.follow_up import FollowUpTask
    from cocli.models.campaigns.indexes.email_pending_batch import PendingBatchEntry

from textual import events, on
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import ListView

from .master_detail import MasterDetailView
from .follow_up_queue_view import FollowUpQueueListItem, FollowUpQueuePreview
from .target_batches_view import PendingBatchListItem, PendingBatchPreview

logger = logging.getLogger(__name__)

_NOT_APPLICABLE_HINTS = {
    "prepare": "Already prepared - use 's' to send.",
    "view": "Only batch drafts have a rendered preview to toggle.",
    "open": "Only batch drafts have a rendered preview to open.",
    "send": "Prepare this follow-up first (p) before it can be sent.",
}


class DraftMessagesView(MasterDetailView):
    """Master: every pending follow-up + every pending batch draft.
    Detail: whichever of the two existing preview widgets matches the
    selected row's type."""

    BINDINGS = [
        Binding("p", "prepare_row", "Prepare", show=True),
        Binding("P", "prepare_all_due", "Prepare All Due", show=True),
        Binding("e", "edit_row", "Edit", show=True),
        Binding("d", "delete_row", "Delete/Discard", show=True),
        Binding("v", "toggle_view_mode", "Toggle HTML/Raw", show=True),
        Binding("o", "open_preview", "Open in Browser", show=True),
        Binding("s", "send_row", "Send Batch", show=True),
        Binding("S", "send_all_batches", "Send All Batches", show=True),
        Binding("n", "new_batch", "New Batch", show=True),
        Binding("ctrl+r", "refresh", "Refresh", show=True),
    ]

    def __init__(self, **kwargs: Any) -> None:
        self.draft_list = ListView(id="draft-message-list")
        self.follow_up_preview = FollowUpQueuePreview(id="fu-queue-preview")
        self.batch_preview = PendingBatchPreview(id="target-batch-preview")
        self._detail_container = Container(self.follow_up_preview, self.batch_preview)
        self._last_g_time: float = 0.0
        self.show_rendered_html: bool = True
        super().__init__(
            master=self.draft_list, detail=self._detail_container, master_width=45, **kwargs
        )

    async def on_mount(self) -> None:
        self.refresh_drafts()

    # ------------------------------------------------------------------
    # List population
    # ------------------------------------------------------------------

    def refresh_drafts(self) -> None:
        from cocli.application.follow_up_service import FollowUpService
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService

        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name

        # Batch drafts (ready to send) surface first - the more actionable
        # of the two stages - followed by not-yet-rendered follow-ups.
        batch_entries = PersonalizedOutreachService(campaign).list_pending_batches()
        follow_up_tasks = FollowUpService(campaign).list_pending()

        self.draft_list.clear()
        for entry in batch_entries:
            self.draft_list.append(PendingBatchListItem(entry))
        for task in follow_up_tasks:
            self.draft_list.append(FollowUpQueueListItem(task))

        if self.draft_list.children:
            self.draft_list.index = 0
            self._show_detail_for(self.draft_list.children[0])
        else:
            self.follow_up_preview.update_preview(None)
            self.batch_preview.update_preview(None, None)
            self.follow_up_preview.display = True
            self.batch_preview.display = False

    def _show_detail_for(self, item: Any) -> None:
        if isinstance(item, PendingBatchListItem):
            self._update_batch_preview(item.entry)
            self.batch_preview.display = True
            self.follow_up_preview.display = False
        elif isinstance(item, FollowUpQueueListItem):
            self.follow_up_preview.update_preview(item.follow_up)
            self.follow_up_preview.display = True
            self.batch_preview.display = False

    def _update_batch_preview(self, entry: "PendingBatchEntry") -> None:
        """Mirrors TargetBatchesView._update_entry_preview exactly (same
        rendered-HTML-vs-raw-markdown logic, same terminal-width-aware
        render)."""
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService
        from cocli.utils.terminal_preview import render_html_for_terminal

        app = cast("CocliApp", self.app)
        service = PersonalizedOutreachService(app.services.campaign_name)
        match = service.entry_to_match(entry)

        rendered_text: str | None = None
        is_html_mode = False

        if self.show_rendered_html:
            try:
                service.ensure_rendered_outreach_draft(entry)
                html_path = service.render_and_save_html_preview(
                    entry.initiative, entry.company_slug, entry.template_id
                )
            except Exception:
                html_path = None

            cols = max(40, self.batch_preview.size.width - 4) if self.batch_preview.size.width > 0 else 76

            if html_path and html_path.exists():
                rendered_text = render_html_for_terminal(html_path, width=cols)
                if rendered_text:
                    is_html_mode = True

            if not rendered_text and match.body and ("<div" in match.body or "<a " in match.body or "<table" in match.body):
                rendered_text = render_html_for_terminal(match.body, width=cols)
                if rendered_text:
                    is_html_mode = True

        self.batch_preview.update_preview(
            match.subject,
            match.body,
            entry=entry,
            rendered_content=rendered_text,
            is_html=is_html_mode,
        )

    # ------------------------------------------------------------------
    # Selection / highlight
    # ------------------------------------------------------------------

    @on(ListView.Selected)
    def on_draft_selected(self, message: ListView.Selected) -> None:
        self._show_detail_for(message.item)

    @on(ListView.Highlighted, "#draft-message-list")
    def on_draft_highlighted(self, message: ListView.Highlighted) -> None:
        if message.item is not None:
            self._show_detail_for(message.item)

    def _highlighted_item(self) -> Any:
        return self.draft_list.highlighted_child

    # ------------------------------------------------------------------
    # Keyboard (vim-nav identical to the two source panes)
    # ------------------------------------------------------------------

    def on_key(self, event: events.Key) -> None:
        if event.key in ("G", "shift+g") or event.character == "G":
            if self.draft_list.children:
                self.draft_list.index = len(self.draft_list.children) - 1
                self.draft_list.scroll_end(animate=False)
            event.prevent_default()
            event.stop()
        elif event.key == "end":
            if self.draft_list.children:
                self.draft_list.index = len(self.draft_list.children) - 1
                self.draft_list.scroll_end(animate=False)
            event.prevent_default()
            event.stop()
        elif event.key == "home":
            if self.draft_list.children:
                self.draft_list.index = 0
                self.draft_list.scroll_home(animate=False)
            event.prevent_default()
            event.stop()
        elif event.key == "g":
            import time

            now = time.time()
            if hasattr(self, "_last_g_time") and (now - self._last_g_time < 0.5):
                self._last_g_time = 0.0
                if self.draft_list.children:
                    self.draft_list.index = 0
                    self.draft_list.scroll_home(animate=False)
                event.prevent_default()
                event.stop()
            else:
                self._last_g_time = now
                event.prevent_default()
                event.stop()
        elif event.key == "j":
            self.draft_list.action_cursor_down()
            event.prevent_default()
            event.stop()
        elif event.key == "k":
            self.draft_list.action_cursor_up()
            event.prevent_default()
            event.stop()

    # ------------------------------------------------------------------
    # Actions - dispatch by row type
    # ------------------------------------------------------------------

    def action_refresh(self) -> None:
        self.refresh_drafts()

    def action_prepare_row(self) -> None:
        item = self._highlighted_item()
        if isinstance(item, FollowUpQueueListItem):
            self.run_worker(self._prepare_single_flow(item.follow_up), exclusive=True)
        elif isinstance(item, PendingBatchListItem):
            self.app.notify(_NOT_APPLICABLE_HINTS["prepare"], severity="warning")
        else:
            self.app.notify("Nothing selected.", severity="warning")

    def action_prepare_all_due(self) -> None:
        self.run_worker(self._prepare_all_flow(), exclusive=True)

    def action_edit_row(self) -> None:
        item = self._highlighted_item()
        if isinstance(item, FollowUpQueueListItem):
            self.run_worker(self._edit_and_prepare_flow(item.follow_up), exclusive=True)
        elif isinstance(item, PendingBatchListItem):
            self.run_worker(self._edit_entry_flow(item.entry), exclusive=True)

    def action_delete_row(self) -> None:
        item = self._highlighted_item()
        if isinstance(item, FollowUpQueueListItem):
            self.run_worker(self._delete_task_flow(item.follow_up), exclusive=True)
        elif isinstance(item, PendingBatchListItem):
            self.run_worker(self._discard_batch_flow(item.entry.batch_id), exclusive=True)

    def action_toggle_view_mode(self) -> None:
        item = self._highlighted_item()
        if not isinstance(item, PendingBatchListItem):
            self.app.notify(_NOT_APPLICABLE_HINTS["view"], severity="warning")
            return
        self.show_rendered_html = not self.show_rendered_html
        self._update_batch_preview(item.entry)
        mode = "Rendered HTML" if self.show_rendered_html else "Raw Markdown"
        self.app.notify(f"Preview mode: {mode}")

    def action_open_preview(self) -> None:
        item = self._highlighted_item()
        if not isinstance(item, PendingBatchListItem):
            self.app.notify(_NOT_APPLICABLE_HINTS["open"], severity="warning")
            return
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService
        from cocli.utils.open_url import open_url

        entry = item.entry
        app = cast("CocliApp", self.app)
        service = PersonalizedOutreachService(app.services.campaign_name)
        service.ensure_rendered_outreach_draft(entry)
        html_path = service.render_and_save_html_preview(
            entry.initiative, entry.company_slug, entry.template_id
        )
        if html_path is None:
            self.app.notify(
                f"No HTML preview for {entry.template_id} (plain-text template)",
                severity="warning",
            )
            return
        if open_url(str(html_path)):
            self.app.notify(f"Opened HTML preview for {entry.company_slug}")
        else:
            self.app.notify(f"Could not open {html_path}", severity="error")

    def action_send_row(self) -> None:
        item = self._highlighted_item()
        if not isinstance(item, PendingBatchListItem):
            self.app.notify(_NOT_APPLICABLE_HINTS["send"], severity="warning")
            return
        self.run_worker(self._send_batch_flow(item.entry.batch_id), exclusive=True)

    def action_send_all_batches(self) -> None:
        self.run_worker(self._send_all_batches_flow(), exclusive=True)

    def action_new_batch(self) -> None:
        self.run_worker(self._new_batch_flow(), exclusive=True)

    # ------------------------------------------------------------------
    # Workers - bodies adapted from FollowUpQueueView / TargetBatchesView
    # ------------------------------------------------------------------

    async def _prepare_single_flow(self, task: "FollowUpTask") -> None:
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
        self.app.notify(f"Prepared {fmt_desc} for {task.company_slug}")
        self.refresh_drafts()

    async def _prepare_all_flow(self) -> None:
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
                f"{result.calls_queued} call follow-up(s)"
            )
        self.refresh_drafts()

    async def _edit_and_prepare_flow(self, task: "FollowUpTask") -> None:
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

        result = await self.app.push_screen_wait(EditPendingEntryModal(subject, body))
        if result is None:
            return
        edited_subject, edited_body = result

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

        try:
            task.get_local_path().unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("Could not remove follow-up queue file: %s", exc)

        self.app.notify(f"Saved edited draft for {task.company_slug}")
        self.refresh_drafts()

    async def _delete_task_flow(self, task: "FollowUpTask") -> None:
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
        self.refresh_drafts()

    async def _edit_entry_flow(self, entry: "PendingBatchEntry") -> None:
        from .edit_pending_entry_modal import EditPendingEntryModal
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService

        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        service = PersonalizedOutreachService(campaign)
        match = service.entry_to_match(entry)
        result = await self.app.push_screen_wait(EditPendingEntryModal(match.subject, match.body))
        if result is None:
            return
        subject, body = result

        service.update_pending_entry(entry.batch_id, entry.company_slug, subject=subject, body=body)
        self.app.notify(f"Updated draft for {entry.company_slug}")
        self.refresh_drafts()

    async def _send_batch_flow(self, batch_id: str) -> None:
        from .confirm_screen import ConfirmScreen
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService

        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        service = PersonalizedOutreachService(campaign)
        count = sum(1 for e in service.list_pending_batches() if e.batch_id == batch_id)

        confirmed = await self.app.push_screen_wait(
            ConfirmScreen(f"Send {count} email(s) in batch {batch_id}?")
        )
        if not confirmed:
            return

        def _send() -> Any:
            from cocli.application.email_service import EmailService
            from cocli.core.config import load_campaign_config
            from cocli.models.mail import EmailSettings

            raw = load_campaign_config(campaign) or {}
            email_raw = raw.get("email") or {}
            settings = EmailSettings.model_validate(email_raw)
            aws = raw.get("aws") or {}
            profile = aws.get("profile") if isinstance(aws.get("profile"), str) else None
            email_service = EmailService(campaign, settings, aws_profile=profile)
            return service.send_pending_batch(batch_id, email_service=email_service)

        try:
            result = await asyncio.to_thread(_send)
        except Exception as e:
            self.app.notify(f"Send failed: {e}", severity="error")
            return

        self.app.notify(f"Batch {result.batch_id}: sent={result.sent} failed={result.failed}")
        self.refresh_drafts()

    async def _send_all_batches_flow(self) -> None:
        from .confirm_screen import ConfirmScreen
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService

        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        service = PersonalizedOutreachService(campaign)
        entries = service.list_pending_batches()
        if not entries:
            self.app.notify("No pending batches to send.", severity="warning")
            return

        confirmed = await self.app.push_screen_wait(
            ConfirmScreen(f"Send all {len(entries)} pending email(s)?")
        )
        if not confirmed:
            return

        def _send() -> tuple[int, int]:
            from cocli.application.email_service import EmailService
            from cocli.core.config import load_campaign_config
            from cocli.models.mail import EmailSettings

            raw = load_campaign_config(campaign) or {}
            email_raw = raw.get("email") or {}
            settings = EmailSettings.model_validate(email_raw)
            aws = raw.get("aws") or {}
            profile = aws.get("profile") if isinstance(aws.get("profile"), str) else None
            email_service = EmailService(campaign, settings, aws_profile=profile)

            total_sent = 0
            total_failed = 0
            batch_ids = list(dict.fromkeys(e.batch_id for e in entries))
            for b_id in batch_ids:
                res = service.send_pending_batch(b_id, email_service=email_service)
                total_sent += res.sent
                total_failed += res.failed
            return total_sent, total_failed

        try:
            sent, failed = await asyncio.to_thread(_send)
        except Exception as e:
            self.app.notify(f"Send failed: {e}", severity="error")
            return

        self.app.notify(f"Sent {sent} email(s) (failed={failed})")
        self.refresh_drafts()

    async def _discard_batch_flow(self, batch_id: str) -> None:
        from .confirm_screen import ConfirmScreen
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService

        confirmed = await self.app.push_screen_wait(
            ConfirmScreen(f"Discard batch {batch_id} without sending?")
        )
        if not confirmed:
            return

        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        service = PersonalizedOutreachService(campaign)
        service.discard_pending_batch(batch_id)
        self.app.notify(f"Discarded batch {batch_id}")
        self.refresh_drafts()

    async def _new_batch_flow(self) -> None:
        from .new_batch_modal import NewBatchModal
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService

        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        service = PersonalizedOutreachService(campaign)
        templates = service.list_templates()

        result = await self.app.push_screen_wait(NewBatchModal(templates))
        if not result:
            return
        limit, template_id = result

        try:
            batch_id = await asyncio.to_thread(
                service.freeze_batch, limit=limit, template_id=template_id
            )
        except Exception as e:
            self.app.notify(f"Could not prepare batch: {e}", severity="error")
            return

        self.app.notify(f"Prepared batch {batch_id}")
        self.refresh_drafts()

    def action_focus_master(self) -> None:
        self.draft_list.focus()
