"""Shared list-item/preview widgets for browsing an email template
rendered with sample values - used by InitiativesView's Email Sequences
category pane (initiatives_view.py)."""

from __future__ import annotations

from typing import Any

from textual.containers import VerticalScroll
from textual.widgets import Label, ListItem, Static


class TemplateListItem(ListItem):
    def __init__(self, template_name: str) -> None:
        super().__init__()
        self.template_name = template_name

    def compose(self) -> Any:
        yield Label(self.template_name)


class TemplatePreview(VerticalScroll):
    DEFAULT_CSS = """
    TemplatePreview #template-preview-tracking-note {
        display: none;
    }
    """

    def compose(self) -> Any:
        yield Label("Select a template to preview it", id="template-preview-empty")
        yield Label("", id="template-preview-subject", classes="detail-row")
        # Mark, 2026-10-07: "I don't even see a placeholder for the GUID
        # ... shouldn't it say something like {utm_guid}?" - by design,
        # no: the token is injected into every link at actual-send time
        # (see cocli/utils/send_tracking.py), not written into the
        # template or shown here - this line exists so that design
        # choice doesn't read as "forgot to add it."
        yield Label(
            "[dim]Links get a unique tracking token (?t=...) appended "
            "automatically at send time - not shown in this preview.[/dim]",
            id="template-preview-tracking-note",
        )
        yield Static("", id="template-preview-body")

    def update_preview(self, subject: str | None, body: str | None) -> None:
        empty = self.query_one("#template-preview-empty", Label)
        subject_label = self.query_one("#template-preview-subject", Label)
        tracking_note = self.query_one("#template-preview-tracking-note", Label)
        body_static = self.query_one("#template-preview-body", Static)
        if subject is None:
            empty.display = True
            subject_label.update("")
            tracking_note.display = False
            body_static.update("")
            return
        empty.display = False
        tracking_note.display = True
        subject_label.update(f"[bold]Subject:[/bold] {subject}")
        body_static.update(body or "")
