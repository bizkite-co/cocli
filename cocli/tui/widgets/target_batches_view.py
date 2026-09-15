"""Review-before-send: browse frozen (not-yet-sent) batches and see the
exact rendered subject/body that would be sent, before it's sent - the
flaw-catching step for template string-substitution errors."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast, TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import CocliApp
    from cocli.models.campaigns.indexes.email_pending_batch import PendingBatchEntry

from textual import events, on
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Label, ListItem, ListView, Static

from .master_detail import MasterDetailView

logger = logging.getLogger(__name__)


class PendingBatchListItem(ListItem):
    def __init__(self, entry: "PendingBatchEntry") -> None:
        super().__init__()
        self.entry = entry

    def compose(self) -> Any:
        e = self.entry
        yield Label(f"[{e.batch_id[:15]}] {e.company_slug} <{e.recipient}> ({e.template_id})")


class PendingBatchPreview(VerticalScroll):
    def compose(self) -> Any:
        yield Label("Select a recipient to review the exact email that would be sent", id="batch-preview-empty")
        yield Label("", id="batch-preview-subject", classes="detail-row")
        yield Static("", id="batch-preview-body")

    def update_preview(self, subject: str | None, body: str | None) -> None:
        empty = self.query_one("#batch-preview-empty", Label)
        subject_label = self.query_one("#batch-preview-subject", Label)
        body_static = self.query_one("#batch-preview-body", Static)
        if subject is None:
            empty.display = True
            subject_label.update("")
            body_static.update("")
            return
        empty.display = False
        subject_label.update(f"[bold]Subject:[/bold] {subject}")
        body_static.update(body or "")


class TargetBatchesView(MasterDetailView):
    """Master: one row per (batch_id, recipient) in every pending batch.
    Detail: that row's exact frozen subject/body. Bindings act on the
    currently-highlighted row's batch_id."""

    BINDINGS = [
        Binding("n", "new_batch", "New Batch", show=True),
        Binding("s", "send_batch", "Send Batch", show=True),
        Binding("d", "discard_batch", "Discard Batch", show=True),
        Binding("ctrl+r", "refresh", "Refresh", show=True),
    ]

    def __init__(self, **kwargs: Any) -> None:
        self.batch_list = ListView(id="target-batch-list")
        self.batch_preview = PendingBatchPreview(id="target-batch-preview")
        super().__init__(master=self.batch_list, detail=self.batch_preview, master_width=45, **kwargs)

    async def on_mount(self) -> None:
        self.refresh_batches()

    def refresh_batches(self) -> None:
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService

        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        service = PersonalizedOutreachService(campaign)
        entries = service.list_pending_batches()

        self.batch_list.clear()
        for entry in entries:
            self.batch_list.append(PendingBatchListItem(entry))

        if not entries:
            self.batch_preview.update_preview(None, None)

    def on_key(self, event: events.Key) -> None:
        """vim-style j/k - ListView only binds arrow keys by default."""
        if event.key == "j":
            self.batch_list.action_cursor_down()
            event.prevent_default()
        elif event.key == "k":
            self.batch_list.action_cursor_up()
            event.prevent_default()

    @on(ListView.Selected)
    def on_batch_row_selected(self, message: ListView.Selected) -> None:
        if not isinstance(message.item, PendingBatchListItem):
            return
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService

        entry = message.item.entry
        match = PersonalizedOutreachService.entry_to_match(entry)
        self.batch_preview.update_preview(match.subject, match.body)

    def _highlighted_entry(self) -> "PendingBatchEntry | None":
        item = self.batch_list.highlighted_child
        if isinstance(item, PendingBatchListItem):
            return item.entry
        return None

    def action_new_batch(self) -> None:
        self.run_worker(self._new_batch_flow(), exclusive=True)

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
        self.refresh_batches()

    def action_send_batch(self) -> None:
        entry = self._highlighted_entry()
        if entry is None:
            return
        self.run_worker(self._send_batch_flow(entry.batch_id), exclusive=True)

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
        self.refresh_batches()

    def action_discard_batch(self) -> None:
        entry = self._highlighted_entry()
        if entry is None:
            return
        self.run_worker(self._discard_batch_flow(entry.batch_id), exclusive=True)

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
        self.refresh_batches()

    def action_refresh(self) -> None:
        self.refresh_batches()
