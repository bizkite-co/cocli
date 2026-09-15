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
    def compose(self) -> Any:
        yield Label("Select a template to preview it", id="template-preview-empty")
        yield Label("", id="template-preview-subject", classes="detail-row")
        yield Static("", id="template-preview-body")

    def update_preview(self, subject: str | None, body: str | None) -> None:
        empty = self.query_one("#template-preview-empty", Label)
        subject_label = self.query_one("#template-preview-subject", Label)
        body_static = self.query_one("#template-preview-body", Static)
        if subject is None:
            empty.display = True
            subject_label.update("")
            body_static.update("")
            return
        empty.display = False
        subject_label.update(f"[bold]Subject:[/bold] {subject}")
        body_static.update(body or "")
