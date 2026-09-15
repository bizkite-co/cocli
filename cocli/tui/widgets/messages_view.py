"""Top-level Messages branch: a Sections sidebar (Initiatives / Target
Batches / Send Log / Unsubscribe Rate) driving a content pane that swaps
between the corresponding section widget - same message-driven swap
pattern as CompanySearchView (TemplateList -> CompanyList)."""

from __future__ import annotations

from typing import Any

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.widgets import Label, ListItem, ListView

from ..base import CocliPanel
from .initiatives_view import InitiativesView
from .target_batches_view import TargetBatchesView
from .send_log_view import SendLogView
from .unsubscribe_rate_view import UnsubscribeRateView

_SECTION_WIDGETS: dict[str, type] = {
    "section_initiatives": InitiativesView,
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
            ListItem(Label("Initiatives"), id="section_initiatives"),
            ListItem(Label("Target Batches"), id="section_batches"),
            ListItem(Label("Send Log"), id="section_send_log"),
            ListItem(Label("Unsubscribe Rate"), id="section_unsubscribe_rate"),
            id="message_sections_list",
        )

    @on(ListView.Selected, "#message_sections_list")
    def on_section_row_selected(self, event: ListView.Selected) -> None:
        if event.item and event.item.id:
            self.post_message(self.SectionSelected(event.item.id))

    def on_key(self, event: events.Key) -> None:
        """vim-style j/k - ListView only binds arrow keys by default (same
        fix as TemplateList.on_key, missed here originally)."""
        list_view = self.query_one("#message_sections_list", ListView)
        if event.key == "j":
            list_view.action_cursor_down()
            event.prevent_default()
        elif event.key == "k":
            list_view.action_cursor_up()
            event.prevent_default()

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
        # Populate the default section's content, but don't focus into it -
        # matches CompanySearchView landing on its Templates sidebar, not
        # the (not-yet-selected) results pane. Calling .focus() on a
        # MasterDetailView content widget here was a no-op anyway (it's a
        # plain Container, not focusable), which left nothing in the DOM
        # actually focused: app.py's _get_active_nav_node() requires
        # has_focus_within to find the active branch, so with nothing
        # focused it found none, "j" had no focused ListView to move, and
        # "h" fell through to the global "Back" binding's no-active-node
        # fallback (action_show_companies) - confirmed 2026-09-15, not a
        # guess.
        await self._show_section("section_initiatives", focus_content=False)
        self.sections_list.focus_list()

    @on(MessageSectionsList.SectionSelected)
    async def on_section_selected(self, message: MessageSectionsList.SectionSelected) -> None:
        await self._show_section(message.section_id)

    async def _show_section(self, section_id: str, *, focus_content: bool = True) -> None:
        widget_cls = _SECTION_WIDGETS.get(section_id)
        if widget_cls is None:
            return
        for child in list(self.content_container.children):
            await child.remove()
        new_widget = widget_cls()
        await self.content_container.mount(new_widget)
        if focus_content and hasattr(new_widget, "action_focus_master"):
            new_widget.action_focus_master()

    def action_focus_sections(self) -> None:
        self.sections_list.focus_list()

    def action_focus_sidebar(self) -> None:
        """Same conventional name app.py's action_navigate_up() already
        looks for (see CompanySearchView/PersonList) - this is what makes
        bare "h" ("Back") return to the Sections list instead of silently
        doing nothing once focus is correctly inside Messages."""
        self.sections_list.focus_list()

    def action_focus_master(self) -> None:
        """Matches the interface app.action_show_messages() expects when
        reusing an already-mounted view (same as EventCurationView, whose
        MasterDetailView base provides this - MessagesView isn't a
        MasterDetailView itself, so it's defined explicitly here)."""
        self.sections_list.focus_list()
