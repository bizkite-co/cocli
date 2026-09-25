# POLICY: frictionless-data-policy-enforcement
from __future__ import annotations

from datetime import datetime, UTC, timedelta
from typing import Optional

from textual import on, events
from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Label, Static

from cocli.application.company_service import format_contact_line, list_known_contacts
from cocli.application.follow_up_service import FollowUpService
from cocli.application.personalized_outreach_service import PersonalizedOutreachService
from cocli.core.config import get_campaign
from cocli.models.companies.company import Company
from cocli.utils.when import parse_follow_up_when
from .inputs import CocliInput
from .search_select import SearchSelect


class EnqueueFollowUpModal(ModalScreen[bool]):
    """Prompts to schedule an email follow-up for a company.
    Allows selecting a contact, selecting an email template, and specifying a due date.
    Dismisses with True if scheduled, False on cancel.
    """

    DEFAULT_CSS = """
    EnqueueFollowUpModal {
        align: center middle;
    }
    #enqueue_follow_up_form {
        width: 78;
        height: 32;
        border: round $primary;
        background: $surface;
        padding: 1 2;
    }
    #enqueue_modal_title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    #enqueue_follow_up_form SearchSelect > ListView {
        max-height: 5;
    }
    #modal_help {
        margin-top: 1;
        text-align: center;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+s", "save", "Enqueue Follow-up"),
    ]

    def __init__(
        self,
        company_slug: str,
        company_name: Optional[str] = None,
        default_contact: Optional[str] = None,
        *args: object,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.company_slug = company_slug
        self.company_name = company_name or company_slug.replace("-", " ").title()
        self.default_contact = default_contact

    def compose(self) -> ComposeResult:
        campaign = get_campaign() or "default"
        service = PersonalizedOutreachService(campaign)
        template_choices_raw = service.list_templates_with_initiative()
        if not template_choices_raw:
            template_choices_raw = [("[rta] email_01_pas_hook.md", "email_01_pas_hook.md", "rta")]

        template_choices: list[tuple[str, str]] = [
            (label, f"{init}::{tpl}") for label, tpl, init in template_choices_raw
        ]

        # Determine smart default template
        company = Company.get(self.company_slug)
        company_tags = (company.tags or []) if company else []
        initial_template = template_choices[0][1]
        if "testimonial-target" in company_tags:
            for label, val in template_choices:
                if "request_testimonial" in val:
                    initial_template = val
                    break

        contacts = list_known_contacts(self.company_slug)
        contact_choices: list[tuple[str, str]] = []
        for c in contacts:
            email = str(c.get("email") or "").strip()
            if not email:
                continue
            line = format_contact_line(c) or email
            contact_choices.append((line, email))

        if not contact_choices:
            if company and company.email:
                co_email = str(company.email).strip()
                contact_choices.append((f"{company.name or self.company_slug} <{co_email}>", co_email))
            else:
                contact_choices.append(("(No contacts on file — company default)", ""))

        # Default callback date: in 3 days
        default_date = (datetime.now(UTC) + timedelta(days=3)).strftime("%Y-%m-%d")

        with Container(id="enqueue_follow_up_form"):
            yield Label(f"ENQUEUE FOLLOW-UP: [bold cyan]{self.company_name}[/]", id="enqueue_modal_title")

            yield Label("Recipient Contact (type to filter, Enter to pick)", classes="field-label")
            yield SearchSelect(
                contact_choices,
                initial_value=contact_choices[0][1] if contact_choices else "",
                id="followup_contact",
            )

            yield Label("Email Template (type to filter, Enter to pick)", classes="field-label")
            yield SearchSelect(
                template_choices,
                initial_value=initial_template,
                id="followup_template",
            )

            yield Label("Scheduled Date (YYYY-MM-DD, 'monday', 'in 3 days')", classes="field-label")
            yield CocliInput(value=default_date, id="followup_date")

            yield Static(
                "[bold reverse] CTRL+S: ENQUEUE [/]  [dim] ESC: CANCEL [/]",
                id="modal_help",
            )

    def on_mount(self) -> None:
        self.query_one("#followup_date", CocliInput).focus()

    @on(events.Key)
    def handle_keys(self, event: events.Key) -> None:
        if event.key == "ctrl+s":
            self.action_save()
            event.prevent_default()
            event.stop()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_save(self) -> None:
        date_str = self.query_one("#followup_date", CocliInput).value.strip()
        try:
            scheduled_date = parse_follow_up_when(date_str)
        except ValueError:
            self.app.notify(f"Invalid date: '{date_str}'", severity="error")
            return

        template_raw = self.query_one("#followup_template", SearchSelect).value
        if not template_raw:
            self.app.notify("Please select an email template", severity="error")
            return

        if "::" in template_raw:
            initiative, template_id = template_raw.split("::", 1)
        else:
            initiative = "rta"
            template_id = template_raw

        recipient_email = self.query_one("#followup_contact", SearchSelect).value

        campaign = get_campaign() or "default"
        company = Company.get(self.company_slug)
        domain = (company.domain if company else None) or "unknown"

        try:
            FollowUpService(campaign).add_follow_up(
                company_slug=self.company_slug,
                domain=domain,
                scheduled_at=scheduled_date,
                format="email",
                template_id=template_id,
                initiative=initiative,
                recipient_email=recipient_email or None,
            )
            self.app.notify(
                f"Scheduled follow-up [{initiative}] ({template_id}) for {scheduled_date.strftime('%Y-%m-%d %H:%M')} UTC"
            )
            self.dismiss(True)
        except Exception as exc:
            self.app.notify(f"Failed to enqueue follow-up: {exc}", severity="error")
