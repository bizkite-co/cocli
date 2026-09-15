"""Browse available email templates, rendered with sample values - lets
you sanity-check a template's placeholders resolve before it's ever used
in a real batch."""

from __future__ import annotations

import logging
from typing import Any, cast, TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import CocliApp

from textual import on
from textual.containers import VerticalScroll
from textual.widgets import Label, ListItem, ListView, Static

from .master_detail import MasterDetailView

logger = logging.getLogger(__name__)


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


class MessageTemplatesView(MasterDetailView):
    """Master: available template filenames. Detail: rendered with
    placeholder sample values (not a real prospect)."""

    def __init__(self, **kwargs: Any) -> None:
        self.template_list = ListView(id="message-template-list")
        self.template_preview = TemplatePreview(id="message-template-preview")
        super().__init__(master=self.template_list, detail=self.template_preview, master_width=30, **kwargs)

    async def on_mount(self) -> None:
        self.refresh_templates()

    def refresh_templates(self) -> None:
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService

        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        service = PersonalizedOutreachService(campaign)
        names = service.list_templates()

        self.template_list.clear()
        for name in names:
            self.template_list.append(TemplateListItem(name))

        if not names:
            self.template_preview.update_preview(None, None)

    @on(ListView.Selected)
    def on_template_selected(self, message: ListView.Selected) -> None:
        if not isinstance(message.item, TemplateListItem):
            return
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService

        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        service = PersonalizedOutreachService(campaign)
        try:
            subject, body = service.generate_copy(
                first_name="Sample",
                company_name="Sample Co",
                company_slug="sample-co",
                template_name=message.item.template_name,
            )
        except Exception as e:
            self.app.notify(f"Template error: {e}", severity="error")
            self.template_preview.update_preview(
                "(template error)", f"{e}\n\nFix the placeholder before using this template in a batch."
            )
            return
        self.template_preview.update_preview(subject, body)
