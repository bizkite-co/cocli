"""A keyboard-only, filterable single-select list - not a GUI dropdown.

Type to filter a fixed list of (label, value) choices; Up/Down to move the
highlighted choice; Enter to select. Built to replace Textual's Select
widget (a mouse-oriented dropdown) in contexts like call disposition,
where this TUI's convention is an always-visible, keyboard-navigable list
(see CompanyList/TemplateList), not a collapsed popup menu.
"""

from __future__ import annotations

from typing import Optional

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Input, Label, ListItem, ListView

from .inputs import CocliInput


class _SearchSelectFilter(CocliInput):
    """Filter box that treats Space as 'pick' when the query is empty."""

    def on_key(self, event: events.Key) -> None:
        if event.key != "space" or self.value.strip():
            return
        select = self.parent
        if not isinstance(select, SearchSelect):
            return
        select._select_current()
        event.stop()
        event.prevent_default()


class SearchSelect(Vertical):
    """Filterable single-select. Posts Selected(value) on Enter."""

    DEFAULT_CSS = """
    SearchSelect {
        height: auto;
    }
    SearchSelect > ListView {
        height: auto;
        max-height: 8;
    }
    SearchSelect > #ss_selected {
        color: #00ff00;
        text-style: bold;
        height: 1;
        margin-bottom: 0;
    }
    SearchSelect ListItem.-highlight {
        background: #00aa00 !important;
        color: #000000 !important;
        text-style: bold;
    }
    """

    class Selected(Message):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def __init__(
        self,
        choices: list[tuple[str, str]],
        *,
        initial_value: Optional[str] = None,
        placeholder: str = "Type to filter...",
        id: Optional[str] = None,
    ) -> None:
        super().__init__(id=id)
        self._all_choices = choices
        self._filtered: list[tuple[str, str]] = list(choices)
        self._placeholder = placeholder
        self.value = initial_value if initial_value is not None else (choices[0][1] if choices else "")

    def compose(self) -> ComposeResult:
        yield Label(self._selected_text(), id="ss_selected")
        yield _SearchSelectFilter(placeholder=self._placeholder, id="ss_filter")
        yield ListView(id="ss_list")

    def _label_for_value(self, value: str) -> str:
        for label, choice_value in self._all_choices:
            if choice_value == value:
                return label
        return value or "(none)"

    def _selected_text(self) -> str:
        return f"Selected: {self._label_for_value(self.value)}  ·  Enter or Space to pick"

    async def on_mount(self) -> None:
        await self._render_list(select_value=self.value)

    async def _render_list(self, select_value: Optional[str] = None) -> None:
        list_view = self.query_one("#ss_list", ListView)
        # ListView.clear() is async - stale nodes are still present (and
        # still hold their ids) until this is awaited, so appending new
        # items with the same ids right after a fire-and-forget clear()
        # raises DuplicateIds. Confirmed 2026-09-14 (test failure, not a
        # guess): typing to re-filter the list crashed with exactly that.
        await list_view.clear()
        for _label, value in self._filtered:
            await list_view.append(ListItem(Label(_label), id=f"ss_opt_{_sanitize(value)}"))
        if not self._filtered:
            return
        index = 0
        if select_value is not None:
            for i, (_label, value) in enumerate(self._filtered):
                if value == select_value:
                    index = i
                    break
        list_view.index = index
        self._refresh_selected_label()

    def _refresh_selected_label(self) -> None:
        self.query_one("#ss_selected", Label).update(self._selected_text())

    async def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "ss_filter":
            return
        query = event.value.strip().lower()
        if query:
            self._filtered = [
                (label, value)
                for label, value in self._all_choices
                if query in label.lower()
            ]
        else:
            self._filtered = list(self._all_choices)
        await self._render_list()
        event.stop()

    def on_key(self, event: events.Key) -> None:
        list_view = self.query_one("#ss_list", ListView)
        if event.key == "down":
            list_view.action_cursor_down()
            self._sync_value_from_index()
            event.stop()
            event.prevent_default()
        elif event.key == "up":
            list_view.action_cursor_up()
            self._sync_value_from_index()
            event.stop()
            event.prevent_default()
        elif event.key == "enter":
            self._select_current()
            event.stop()
            event.prevent_default()
        elif event.key == "space":
            # Space picks the highlighted row only when the filter is
            # empty, so typing "Wrong Trade" can still use spaces.
            if not self.query_one("#ss_filter", CocliInput).value.strip():
                self._select_current()
                event.stop()
                event.prevent_default()

    def _sync_value_from_index(self) -> None:
        list_view = self.query_one("#ss_list", ListView)
        index = list_view.index
        if index is not None and 0 <= index < len(self._filtered):
            self.value = self._filtered[index][1]
            self._refresh_selected_label()

    def _select_current(self) -> None:
        list_view = self.query_one("#ss_list", ListView)
        index = list_view.index
        if index is not None and 0 <= index < len(self._filtered):
            _, value = self._filtered[index]
            self.value = value
            self._refresh_selected_label()
            self.post_message(self.Selected(value))

    def focus_filter(self) -> None:
        self.query_one("#ss_filter", CocliInput).focus()


def _sanitize(value: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in value)
