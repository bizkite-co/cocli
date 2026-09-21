"""Browse recently logged phone calls and their notes."""

from __future__ import annotations

import asyncio
from typing import Any, cast, TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import CocliApp
    from cocli.models.companies.meeting import CompanyCall

from textual import events, on, work
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Label, ListItem, ListView, Static

from .master_detail import MasterDetailView


class RecentCallListItem(ListItem):
    def __init__(self, call: "CompanyCall") -> None:
        super().__init__()
        self.call = call

    def compose(self) -> Any:
        yield Label(
            f"{self.call.datetime_local:%Y-%m-%d %H:%M}  "
            f"{self.call.company_name} - {self.call.title}"
        )


class RecentCallPreview(VerticalScroll):
    def compose(self) -> Any:
        yield Label("Select a call to see its notes", id="recent-call-preview-empty")
        yield Static("", id="recent-call-preview-body")

    def update_preview(self, call: "CompanyCall | None") -> None:
        empty = self.query_one("#recent-call-preview-empty", Label)
        body = self.query_one("#recent-call-preview-body", Static)
        if call is None:
            empty.display = True
            body.update("")
            return
        empty.display = False
        body.update(
            "\n".join(
                [
                    f"[bold]Company:[/bold] {call.company_name}",
                    f"[bold]When:[/bold] {call.datetime_local:%Y-%m-%d %H:%M %Z}",
                    f"[bold]Call:[/bold] {call.title}",
                    "",
                    call.content or "[dim]No call notes recorded[/dim]",
                    "",
                    "[dim]l: open company[/dim]",
                ]
            )
        )


class RecentCallsView(MasterDetailView):
    """Master: recent calls, newest first. Detail: the logged call notes."""

    BINDINGS = [Binding("ctrl+r", "refresh", "Refresh", show=True)]

    def __init__(self, **kwargs: Any) -> None:
        self.call_list = ListView(id="recent-call-list")
        self.call_preview = RecentCallPreview(id="recent-call-preview")
        super().__init__(master=self.call_list, detail=self.call_preview, master_width=45, **kwargs)

    async def on_mount(self) -> None:
        self.refresh_calls()

    def refresh_calls(self) -> None:
        app = cast("CocliApp", self.app)
        calls = app.services.meeting_service.get_recent_calls()
        self.call_list.clear()
        for call in calls:
            self.call_list.append(RecentCallListItem(call))
        if calls:
            self.call_list.index = 0
            self.call_preview.update_preview(calls[0])
        else:
            self.call_preview.update_preview(None)

    @on(ListView.Selected)
    def on_call_selected(self, message: ListView.Selected) -> None:
        if isinstance(message.item, RecentCallListItem):
            self.call_preview.update_preview(message.item.call)

    @on(ListView.Highlighted, "#recent-call-list")
    def on_call_highlighted(self, message: ListView.Highlighted) -> None:
        if isinstance(message.item, RecentCallListItem):
            self.debounce_highlight()

    @work(exclusive=True)
    async def debounce_highlight(self) -> None:
        """Preview the row that remains highlighted for the standard delay."""
        await asyncio.sleep(0.25)
        item = self.call_list.highlighted_child
        if isinstance(item, RecentCallListItem):
            self.call_preview.update_preview(item.call)

    def on_key(self, event: events.Key) -> None:
        if event.key == "j":
            self.call_list.action_cursor_down()
            event.prevent_default()
            event.stop()
        elif event.key == "k":
            self.call_list.action_cursor_up()
            event.prevent_default()
            event.stop()
        elif event.key == "l":
            item = self.call_list.highlighted_child
            if isinstance(item, RecentCallListItem):
                cast("CocliApp", self.app).open_company_detail(
                    item.call.company_slug,
                    return_to_messages_recent_calls=True,
                )
            event.prevent_default()
            event.stop()

    def action_refresh(self) -> None:
        self.refresh_calls()
