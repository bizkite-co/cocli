"""Top-level Messages branch: a Sections sidebar (Templates / Target
Batches / Send Log / Unsubscribe Rate) driving a content pane that swaps
between the corresponding section widget - same message-driven swap
pattern as CompanySearchView (TemplateList -> CompanyList)."""

from __future__ import annotations

from typing import Any

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.widgets import Label, ListItem, ListView

from ..base import CocliPanel
from .message_templates_view import MessageTemplatesView
from .target_batches_view import TargetBatchesView
from .send_log_view import SendLogView
from .unsubscribe_rate_view import UnsubscribeRateView

_SECTION_WIDGETS: dict[str, type] = {
    "section_templates": MessageTemplatesView,
    "section_batches": TargetBatchesView,
    "section_send_log": SendLogView,
    "section_unsubscribe_rate": UnsubscribeRateView,
}


class MessageSectionsList(CocliPanel):
    """The left-hand sidebar - which Messages section is active."""

    class SectionSelected(Message):
        def __init__(self, section_id: str) -> None:
            super().__init__()
            self.section_id = section_id

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(panel_title="SECTIONS", **kwargs)

    def compose(self) -> ComposeResult:
        yield Label("SECTIONS", classes="pane-header")
        yield ListView(
            ListItem(Label("Templates"), id="section_templates"),
            ListItem(Label("Target Batches"), id="section_batches"),
            ListItem(Label("Send Log"), id="section_send_log"),
            ListItem(Label("Unsubscribe Rate"), id="section_unsubscribe_rate"),
            id="message_sections_list",
        )

    @on(ListView.Selected, "#message_sections_list")
    def on_section_row_selected(self, event: ListView.Selected) -> None:
        if event.item and event.item.id:
            self.post_message(self.SectionSelected(event.item.id))

    def focus_list(self) -> None:
        self.query_one(ListView).focus()


class MessagesView(Container):
    """The Messages branch root (is_branch_root=True in app.py's nav_tree)."""

    BINDINGS = [
        ("t", "focus_sections", "Focus Sections"),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.sections_list = MessageSectionsList(id="message-sections")
        self.content_container: Container = Container(id="messages-content")

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield self.sections_list
            yield self.content_container

    async def on_mount(self) -> None:
        await self._show_section("section_templates")

    @on(MessageSectionsList.SectionSelected)
    async def on_section_selected(self, message: MessageSectionsList.SectionSelected) -> None:
        await self._show_section(message.section_id)

    async def _show_section(self, section_id: str) -> None:
        widget_cls = _SECTION_WIDGETS.get(section_id)
        if widget_cls is None:
            return
        for child in list(self.content_container.children):
            await child.remove()
        new_widget = widget_cls()
        await self.content_container.mount(new_widget)
        new_widget.focus()

    def action_focus_sections(self) -> None:
        self.sections_list.focus_list()

    def action_focus_master(self) -> None:
        """Matches the interface app.action_show_messages() expects when
        reusing an already-mounted view (same as EventCurationView, whose
        MasterDetailView base provides this - MessagesView isn't a
        MasterDetailView itself, so it's defined explicitly here)."""
        self.sections_list.focus_list()
