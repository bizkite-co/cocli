"""Browse recent emails (inbound and outbound) with full body content and company context."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, UTC
from typing import Any, cast, TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import CocliApp
    from cocli.models.campaigns.indexes.email_send_log import SendLogEntry

from textual import events, on, work
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Label, ListItem, ListView, Static

from cocli.models.companies.email_note import CompanyEmail
from .master_detail import MasterDetailView

logger = logging.getLogger(__name__)


class RecentEmailListItem(ListItem):
    def __init__(self, email: "CompanyEmail | SendLogEntry") -> None:
        super().__init__()
        if not isinstance(email, CompanyEmail):
            local_tz: Any
            try:
                from tzlocal import get_localzone

                local_tz = get_localzone()
            except Exception:
                local_tz = UTC
            dt_utc = getattr(email, "sent_at", None) or datetime.now(UTC)
            dt_local = dt_utc.astimezone(local_tz)
            co_slug = getattr(email, "company_slug", "")
            self.email = CompanyEmail(
                datetime_utc=dt_utc,
                datetime_local=dt_local,
                company_name=co_slug.replace("-", " ").title() if co_slug else "(Unknown)",
                company_slug=co_slug,
                title=getattr(email, "subject", "") or "(no subject)",
                direction="sent",
                from_address="",
                to_addresses=[getattr(email, "recipient", "")],
                content=(
                    f"(Batch send: {getattr(email, 'batch_id', '')}, template: {getattr(email, 'template_id', '')})"
                    if not getattr(email, "error", None)
                    else f"Error: {getattr(email, 'error', '')}"
                ),
                message_id=getattr(email, "message_id", None),
                status=getattr(email, "status", "sent"),
                batch_id=getattr(email, "batch_id", None),
                template_id=getattr(email, "template_id", None),
                error=getattr(email, "error", None),
                initiative=getattr(email, "initiative", None),
            )
        else:
            self.email = email
        self.entry = self.email

    def compose(self) -> Any:
        e = self.email
        badge = (
            "[cyan][RCVD][/cyan]"
            if e.direction == "received"
            else ("[red][FAIL][/red]" if e.status == "failed" else "[green][SENT][/green]")
        )
        dt_str = e.datetime_local.strftime("%m-%d %H:%M")
        co_label = e.company_slug or e.company_name
        snippet = (e.content or "").strip().replace("\n", " ")
        if len(snippet) > 80:
            snippet = snippet[:77] + "..."
        snippet_line = f"\n   [dim]{snippet}[/dim]" if snippet else ""
        yield Label(
            f"{badge} {dt_str} {co_label} - {e.title}{snippet_line}"
        )


class RecentEmailDetail(VerticalScroll):
    def compose(self) -> Any:
        yield Label("Select an email to see details", id="send-log-detail-empty")
        yield Static("", id="send-log-detail-body")

    def update_entry(self, entry: "CompanyEmail | SendLogEntry | None") -> None:
        empty = self.query_one("#send-log-detail-empty", Label)
        body = self.query_one("#send-log-detail-body", Static)
        if entry is None:
            empty.display = True
            body.update("")
            return
        empty.display = False

        if not isinstance(entry, CompanyEmail):
            local_tz: Any
            try:
                from tzlocal import get_localzone

                local_tz = get_localzone()
            except Exception:
                local_tz = UTC
            dt_utc = getattr(entry, "sent_at", None) or datetime.now(UTC)
            dt_local = dt_utc.astimezone(local_tz)
            co_slug = getattr(entry, "company_slug", "")
            e = CompanyEmail(
                datetime_utc=dt_utc,
                datetime_local=dt_local,
                company_name=co_slug.replace("-", " ").title() if co_slug else "(Unknown)",
                company_slug=co_slug,
                title=getattr(entry, "subject", "") or "(no subject)",
                direction="sent",
                from_address="",
                to_addresses=[getattr(entry, "recipient", "")],
                content=(
                    f"(Batch send: {getattr(entry, 'batch_id', '')}, template: {getattr(entry, 'template_id', '')})"
                    if not getattr(entry, "error", None)
                    else f"Error: {getattr(entry, 'error', '')}"
                ),
                message_id=getattr(entry, "message_id", None),
                status=getattr(entry, "status", "sent"),
                batch_id=getattr(entry, "batch_id", None),
                template_id=getattr(entry, "template_id", None),
                error=getattr(entry, "error", None),
                initiative=getattr(entry, "initiative", None),
            )
        else:
            e = entry

        dt_str = e.datetime_local.strftime("%m-%d %H:%M %Z")
        badge = (
            "[cyan]RECEIVED[/cyan]"
            if e.direction == "received"
            else ("[red]FAILED[/red]" if e.status == "failed" else "[green]SENT[/green]")
        )
        lines = [
            f"[bold]Direction:[/bold] {badge}",
            f"[bold]Company:[/bold] {e.company_name} ({e.company_slug})",
            f"[bold]When:[/bold] {dt_str}",
            f"[bold]From:[/bold] {e.from_address or 'n/a'}",
            f"[bold]To:[/bold] {', '.join(e.to_addresses) if e.to_addresses else (e.recipient or 'n/a')}",
            f"[bold]Subject:[/bold] {e.title}",
        ]
        if e.message_id:
            lines.append(f"[bold]Message ID:[/bold] {e.message_id}")
        if e.batch_id:
            lines.append(f"[bold]Batch:[/bold] {e.batch_id} (Template: {e.template_id or 'n/a'})")
        if e.error:
            lines.append(f"[bold red]Error:[/bold red] {e.error}")

        lines.extend([
            "",
            "[bold]Content:[/bold]",
            e.content or "[dim](No content recorded)[/dim]",
        ])

        if e.company_slug:
            from cocli.application.company_service import get_company_activity

            activities = get_company_activity(e.company_slug)
            if activities:
                lines.extend(["", "─" * 40, "[bold cyan]Company Activity:[/bold cyan]"])
                for act in activities[:6]:
                    ts_str = act.timestamp.strftime("%m-%d %H:%M")
                    lines.append(f"  {act.icon} [dim]{ts_str}[/dim] {act.preview}")

        lines.extend([
            "",
            "─" * 40,
            "[dim]f: follow-up email    l: open company[/dim]",
        ])
        body.update("\n".join(lines))


class RecentEmailsView(MasterDetailView):
    """Master: recent emails (inbound & outbound), newest first. Detail: full content and metadata."""

    BINDINGS = [
        Binding("ctrl+r", "refresh", "Refresh", show=True),
        Binding("f", "enqueue_follow_up", "Follow-up", show=True),
    ]

    def __init__(self, **kwargs: Any) -> None:
        self.log_list = ListView(id="send-log-list")
        self.log_detail = RecentEmailDetail(id="send-log-detail")
        super().__init__(master=self.log_list, detail=self.log_detail, master_width=45, **kwargs)

    async def on_mount(self) -> None:
        self.refresh_log()

    def refresh_log(self, use_cache: bool = True) -> None:
        app = cast("CocliApp", self.app)
        emails = app.services.email_service.get_recent_emails(use_cache=use_cache)

        self.log_list.clear()
        for email in emails:
            self.log_list.append(RecentEmailListItem(email))

        if emails:
            self.log_list.index = 0
            self.log_detail.update_entry(emails[0])
        else:
            self.log_detail.update_entry(None)

    def on_key(self, event: events.Key) -> None:
        """vim-style j/k/l - ListView only binds arrow keys by default."""
        if event.key == "j":
            self.log_list.action_cursor_down()
            event.prevent_default()
            event.stop()
        elif event.key == "k":
            self.log_list.action_cursor_up()
            event.prevent_default()
            event.stop()
        elif event.key == "l":
            item = self.log_list.highlighted_child
            if isinstance(item, RecentEmailListItem) and item.email.company_slug:
                cast("CocliApp", self.app).open_company_detail(
                    item.email.company_slug,
                    return_to_messages_recent_calls=True,
                )
            event.prevent_default()
            event.stop()
        elif event.key == "f":
            self.action_enqueue_follow_up()
            event.prevent_default()
            event.stop()

    @on(ListView.Selected)
    def on_log_entry_selected(self, message: ListView.Selected) -> None:
        if isinstance(message.item, RecentEmailListItem):
            self.log_detail.update_entry(message.item.email)

    @on(ListView.Highlighted, "#send-log-list")
    def on_log_entry_highlighted(self, message: ListView.Highlighted) -> None:
        if isinstance(message.item, RecentEmailListItem):
            self.debounce_highlight()

    @work(exclusive=True)
    async def debounce_highlight(self) -> None:
        await asyncio.sleep(0.25)
        item = self.log_list.highlighted_child
        if isinstance(item, RecentEmailListItem):
            self.log_detail.update_entry(item.email)

    def action_enqueue_follow_up(self) -> None:
        item = self.log_list.highlighted_child
        if not isinstance(item, RecentEmailListItem) or not item.email.company_slug:
            return
        from .enqueue_follow_up_modal import EnqueueFollowUpModal

        def on_dismiss(result: bool | None) -> None:
            if result:
                self.log_detail.update_entry(item.email)

        self.app.push_screen(
            EnqueueFollowUpModal(
                company_slug=item.email.company_slug,
                company_name=item.email.company_name,
            ),
            on_dismiss,
        )

    def action_refresh(self) -> None:
        self.refresh_log(use_cache=False)

    def action_focus_master(self) -> None:
        self.log_list.focus()


# Backward compatibility aliases
SendLogListItem = RecentEmailListItem
SendLogDetail = RecentEmailDetail
SendLogView = RecentEmailsView
