"""Browse the structured send log (SendLogEntry) - what was actually sent,
to whom, in which batch, and whether it succeeded."""

from __future__ import annotations

import logging
from typing import Any, cast, TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import CocliApp
    from cocli.models.campaigns.indexes.email_send_log import SendLogEntry

from textual import events, on
from textual.containers import VerticalScroll
from textual.widgets import Label, ListItem, ListView

from .master_detail import MasterDetailView

logger = logging.getLogger(__name__)


class SendLogListItem(ListItem):
    def __init__(self, entry: "SendLogEntry") -> None:
        super().__init__()
        self.entry = entry

    def compose(self) -> Any:
        e = self.entry
        status_style = "green" if e.status == "sent" else "red"
        yield Label(
            f"[{status_style}]{e.status.upper()}[/] {e.sent_at:%Y-%m-%d %H:%M} "
            f"{e.company_slug} <{e.recipient}>"
        )


class SendLogDetail(VerticalScroll):
    def compose(self) -> Any:
        yield Label("Select a send log entry to see details", id="send-log-detail-empty")
        yield Label("", id="send-log-detail-body")

    def update_entry(self, entry: "SendLogEntry | None") -> None:
        empty = self.query_one("#send-log-detail-empty", Label)
        body = self.query_one("#send-log-detail-body", Label)
        if entry is None:
            empty.display = True
            body.update("")
            return
        empty.display = False
        lines = [
            f"[bold]Batch:[/bold] {entry.batch_id}",
            f"[bold]Template:[/bold] {entry.template_id}",
            f"[bold]Company:[/bold] {entry.company_slug}",
            f"[bold]Recipient:[/bold] {entry.recipient}",
            f"[bold]Subject:[/bold] {entry.subject}",
            f"[bold]Status:[/bold] {entry.status}",
            f"[bold]Sent at:[/bold] {entry.sent_at:%Y-%m-%d %H:%M:%S}",
            f"[bold]Message ID:[/bold] {entry.message_id or 'n/a'}",
        ]
        if entry.error:
            lines.append(f"[bold red]Error:[/bold red] {entry.error}")
        body.update("\n".join(lines))


class SendLogView(MasterDetailView):
    """Master: SendLogEntry rows, newest first. Detail: full row."""

    def __init__(self, **kwargs: Any) -> None:
        self.log_list = ListView(id="send-log-list")
        self.log_detail = SendLogDetail(id="send-log-detail")
        super().__init__(master=self.log_list, detail=self.log_detail, master_width=45, **kwargs)

    async def on_mount(self) -> None:
        self.refresh_log()

    def refresh_log(self) -> None:
        from cocli.models.campaigns.indexes.email_send_log import SendLogEntry

        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        log_path = SendLogEntry.get_index_dir(campaign) / "log.usv"

        entries: list[SendLogEntry] = []
        if log_path.exists():
            for line in log_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    entries.append(SendLogEntry.from_usv(line))
                except Exception:
                    continue
        entries.sort(key=lambda e: e.sent_at, reverse=True)

        self.log_list.clear()
        for entry in entries:
            self.log_list.append(SendLogListItem(entry))

        if not entries:
            self.log_detail.update_entry(None)

    def on_key(self, event: events.Key) -> None:
        """vim-style j/k - ListView only binds arrow keys by default."""
        if event.key == "j":
            self.log_list.action_cursor_down()
            event.prevent_default()
        elif event.key == "k":
            self.log_list.action_cursor_up()
            event.prevent_default()

    @on(ListView.Selected)
    def on_log_entry_selected(self, message: ListView.Selected) -> None:
        if isinstance(message.item, SendLogListItem):
            self.log_detail.update_entry(message.item.entry)
