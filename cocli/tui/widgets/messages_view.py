"""Top-level Messages branch (Space m)."""

from __future__ import annotations

from typing import Any

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Label, ListItem, ListView

from .initiatives_view import InitiativesView
from .recent_calls_view import RecentCallsView
from .send_log_view import SendLogView
from .target_batches_view import TargetBatchesView


class MessagesSectionItem(ListItem):
    def __init__(self, section: str, label: str) -> None:
        super().__init__()
        self.section = section
        self.label = label

    def compose(self) -> ComposeResult:
        yield Label(self.label)


class MessagesView(Container):
    """Message operations: drafts, call history, campaign copy, and sent email."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.section_list = ListView(
            MessagesSectionItem("follow-ups", "Follow-up Drafts"),
            MessagesSectionItem("batch-emails", "Batch Email Drafts"),
            MessagesSectionItem("recent-calls", "Recent Calls"),
            MessagesSectionItem("initiatives", "Initiatives"),
            MessagesSectionItem("sent-email", "Sent Email"),
            id="messages-section-list",
        )
        self.content = Container(id="messages-content")

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="messages-sidebar"):
                yield Label("Messages", classes="sidebar-title")
                yield self.section_list
            yield self.content

    async def on_mount(self) -> None:
        self.section_list.index = 0
        await self._show_section("follow-ups", focus=False)
        self.action_focus_master()

    def action_focus_sidebar(self) -> None:
        self.action_focus_master()

    def action_focus_master(self) -> None:
        self.section_list.focus()

    def action_focus_recent_calls(self) -> None:
        recent_calls = self.content.query_one(RecentCallsView)
        recent_calls.action_focus_master()

    @on(ListView.Selected, "#messages-section-list")
    async def on_section_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, MessagesSectionItem):
            await self._show_section(event.item.section, focus=True)

    async def _show_section(self, section: str, focus: bool = False) -> None:
        from .follow_up_queue_view import FollowUpQueueView

        view_classes = {
            "follow-ups": FollowUpQueueView,
            "batch-emails": TargetBatchesView,
            "recent-calls": RecentCallsView,
            "initiatives": InitiativesView,
            "sent-email": SendLogView,
        }
        target_cls = view_classes.get(section, SendLogView)

        current_view = self.content.children[0] if self.content.children else None
        if current_view is not None and isinstance(current_view, target_cls):
            if focus and hasattr(current_view, "action_focus_master"):
                current_view.action_focus_master()
            return

        for child in list(self.content.children):
            await child.remove()

        view = target_cls()
        await self.content.mount(view)
        if focus and hasattr(view, "action_focus_master"):
            view.action_focus_master()

    def on_key(self, event: events.Key) -> None:
        if self.app.focused is not self.section_list:
            return
        if event.key == "j":
            self.section_list.action_cursor_down()
        elif event.key == "k":
            self.section_list.action_cursor_up()
        elif event.key in ("l", "enter"):
            self.section_list.action_select_cursor()
        elif event.key != "h":
            return
        event.prevent_default()
        event.stop()
