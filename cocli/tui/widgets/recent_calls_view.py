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
        icon = self.call.icon or ("💬" if self.call.item_type == "sms" else "📞")
        dir_badge = (
            f"[{self.call.direction.upper()}] "
            if self.call.item_type == "sms" and self.call.direction
            else ""
        )
        dt_str = self.call.datetime_local.strftime("%m-%d %H:%M")
        yield Label(
            f"{icon} {dt_str}  "
            f"{self.call.company_name} - {dir_badge}{self.call.title}"
        )


class RecentCallPreview(VerticalScroll):
    def compose(self) -> Any:
        yield Label(
            "Select a call or SMS to see its details", id="recent-call-preview-empty"
        )
        yield Static("", id="recent-call-preview-body")

    def update_preview(self, call: "CompanyCall | None") -> None:
        empty = self.query_one("#recent-call-preview-empty", Label)
        body = self.query_one("#recent-call-preview-body", Static)
        if call is None:
            empty.display = True
            body.update("")
            return
        empty.display = False

        from cocli.application.company_service import get_company_activity

        activity_lines: list[str] = []
        if call.company_slug:
            activities = get_company_activity(call.company_slug)
            if activities:
                activity_lines.append("[bold cyan]Company Activity:[/bold cyan]")
                for act in activities[:6]:
                    ts_str = act.timestamp.strftime("%m-%d %H:%M")
                    activity_lines.append(f"  {act.icon} [dim]{ts_str}[/dim] {act.preview}")
        if not activity_lines:
            activity_lines.append("[dim]No previous activity logged[/dim]")

        item_label = "SMS" if call.item_type == "sms" else "Call"
        content_header = "Content:" if call.item_type == "sms" else "Notes:"
        dir_str = f" ({call.direction})" if call.direction else ""

        preview_text = "\n".join(
            [
                f"[bold]Company:[/bold] {call.company_name}",
                f"[bold]When:[/bold] {call.datetime_local:%m-%d %H:%M %Z}",
                f"[bold]{item_label}{dir_str}:[/bold] {call.title}",
                "",
                f"[bold]{content_header}[/bold]",
                call.content or f"[dim]No {item_label.lower()} content recorded[/dim]",
                "",
                "─" * 40,
                *activity_lines,
                "─" * 40,
                "",
                "[dim]f: follow-up email    l: open company[/dim]",
            ]
        )
        body.update(preview_text)


class RecentCallsView(MasterDetailView):
    """Master: recent calls, newest first. Detail: the logged call notes."""

    BINDINGS = [
        Binding("ctrl+r", "refresh", "Refresh", show=True),
        Binding("f", "enqueue_follow_up", "Follow-up", show=True),
    ]

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
        elif event.key == "f":
            self.action_enqueue_follow_up()
            event.prevent_default()
            event.stop()

    def action_enqueue_follow_up(self) -> None:
        item = self.call_list.highlighted_child
        if not isinstance(item, RecentCallListItem):
            return
        from .enqueue_follow_up_modal import EnqueueFollowUpModal

        def on_dismiss(result: bool | None) -> None:
            if result:
                self.call_preview.update_preview(item.call)

        self.app.push_screen(
            EnqueueFollowUpModal(
                company_slug=item.call.company_slug,
                company_name=item.call.company_name,
            ),
            on_dismiss,
        )

    def action_refresh(self) -> None:
        app = cast("CocliApp", self.app)
        app.services.meeting_service.rebuild_recent_calls_cache()
        self.refresh_calls()

