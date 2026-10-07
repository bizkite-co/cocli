"""Browse recent calls, SMS, and emails together in one newest-first list
(Mark, 2026-10-07: "combine 'Recent Calls & SMS' and 'Recent Emails' into
a 'Recent Messages' ... We would just need a message type indicator icon
like we are already using in several of the lists").

Reuses RecentCallListItem/RecentCallPreview and RecentEmailListItem/
RecentEmailDetail as-is (both already carry their own message-type icon -
"📞"/"💬" and a [SENT]/[RCVD]/[FAIL] badge respectively) rather than
inventing a new unified item/record type - the two previews are mounted
side by side and swapped by visibility depending on which kind of row is
selected, so all existing rendering/detail logic (including the
"Company Activity" sidebar in each) is untouched.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast, TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import CocliApp

from textual import events, on, work
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import ListView

from .master_detail import MasterDetailView
from .recent_calls_view import RecentCallListItem, RecentCallPreview
from .send_log_view import RecentEmailDetail, RecentEmailListItem


class RecentMessagesView(MasterDetailView):
    """Master: recent calls, SMS, and emails, newest first, interleaved.
    Detail: whichever of the two existing preview widgets matches the
    selected row's type."""

    BINDINGS = [
        Binding("ctrl+r", "refresh", "Refresh", show=True),
        Binding("f", "enqueue_follow_up", "Follow-up", show=True),
    ]

    def __init__(self, **kwargs: Any) -> None:
        self.message_list = ListView(id="recent-message-list")
        self.call_preview = RecentCallPreview(id="recent-call-preview")
        self.email_detail = RecentEmailDetail(id="send-log-detail")
        self._detail_container = Container(self.call_preview, self.email_detail)
        self._last_g_time: float = 0.0
        super().__init__(master=self.message_list, detail=self._detail_container, master_width=45, **kwargs)

    async def on_mount(self) -> None:
        self.refresh_messages()

    def refresh_messages(self, use_cache: bool = True) -> None:
        app = cast("CocliApp", self.app)
        calls = app.services.meeting_service.get_recent_calls()
        emails = app.services.email_service.get_recent_emails(use_cache=use_cache)

        items: list[Any] = [RecentCallListItem(c) for c in calls] + [
            RecentEmailListItem(e) for e in emails
        ]
        items.sort(key=self._item_timestamp, reverse=True)

        self.message_list.clear()
        for item in items:
            self.message_list.append(item)

        if items:
            self.message_list.index = 0
            self._show_detail_for(items[0])
        else:
            self.call_preview.update_preview(None)
            self.email_detail.update_entry(None)
            self.call_preview.display = True
            self.email_detail.display = False

    @staticmethod
    def _item_timestamp(item: Any) -> Any:
        if isinstance(item, RecentCallListItem):
            return item.call.datetime_utc
        return item.email.datetime_utc

    def _show_detail_for(self, item: Any) -> None:
        if isinstance(item, RecentCallListItem):
            self.call_preview.update_preview(item.call)
            self.call_preview.display = True
            self.email_detail.display = False
        elif isinstance(item, RecentEmailListItem):
            self.email_detail.update_entry(item.email)
            self.email_detail.display = True
            self.call_preview.display = False

    @on(ListView.Selected)
    def on_message_selected(self, message: ListView.Selected) -> None:
        self._show_detail_for(message.item)

    @on(ListView.Highlighted, "#recent-message-list")
    def on_message_highlighted(self, message: ListView.Highlighted) -> None:
        if message.item is not None:
            self.debounce_highlight()

    @work(exclusive=True)
    async def debounce_highlight(self) -> None:
        """Preview the row that remains highlighted for the standard delay."""
        await asyncio.sleep(0.25)
        item = self.message_list.highlighted_child
        if item is not None:
            self._show_detail_for(item)

    def on_key(self, event: events.Key) -> None:
        if event.key in ("G", "shift+g") or event.character == "G":
            if self.message_list.children:
                self.message_list.index = len(self.message_list.children) - 1
                self.message_list.scroll_end(animate=False)
            event.prevent_default()
            event.stop()
        elif event.key == "end":
            if self.message_list.children:
                self.message_list.index = len(self.message_list.children) - 1
                self.message_list.scroll_end(animate=False)
            event.prevent_default()
            event.stop()
        elif event.key == "home":
            if self.message_list.children:
                self.message_list.index = 0
                self.message_list.scroll_home(animate=False)
            event.prevent_default()
            event.stop()
        elif event.key == "g":
            import time

            now = time.time()
            if hasattr(self, "_last_g_time") and (now - self._last_g_time < 0.5):
                self._last_g_time = 0.0
                if self.message_list.children:
                    self.message_list.index = 0
                    self.message_list.scroll_home(animate=False)
                event.prevent_default()
                event.stop()
            else:
                self._last_g_time = now
                event.prevent_default()
                event.stop()
        elif event.key == "j":
            self.message_list.action_cursor_down()
            event.prevent_default()
            event.stop()
        elif event.key == "k":
            self.message_list.action_cursor_up()
            event.prevent_default()
            event.stop()
        elif event.key == "l":
            item = self.message_list.highlighted_child
            slug = None
            if isinstance(item, RecentCallListItem):
                slug = item.call.company_slug
            elif isinstance(item, RecentEmailListItem):
                slug = item.email.company_slug
            if slug:
                cast("CocliApp", self.app).open_company_detail(
                    slug,
                    return_to_messages=True,
                    return_to_messages_section="recent-messages",
                )
            event.prevent_default()
            event.stop()
        elif event.key == "f":
            self.action_enqueue_follow_up()
            event.prevent_default()
            event.stop()

    def action_enqueue_follow_up(self) -> None:
        item = self.message_list.highlighted_child
        if isinstance(item, RecentCallListItem):
            company_slug = item.call.company_slug
            company_name = item.call.company_name
        elif isinstance(item, RecentEmailListItem):
            if not item.email.company_slug:
                return
            company_slug = item.email.company_slug
            company_name = item.email.company_name
        else:
            return

        from .enqueue_follow_up_modal import EnqueueFollowUpModal

        def on_dismiss(result: bool | None) -> None:
            if result:
                self._show_detail_for(item)

        self.app.push_screen(
            EnqueueFollowUpModal(company_slug=company_slug, company_name=company_name),
            on_dismiss,
        )

    def action_refresh(self) -> None:
        app = cast("CocliApp", self.app)
        app.services.meeting_service.rebuild_recent_calls_cache()
        self.refresh_messages(use_cache=False)

    def action_focus_master(self) -> None:
        self.message_list.focus()
