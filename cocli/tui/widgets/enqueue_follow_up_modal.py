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
        ("f4", "send_now", "Send Now"),
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
                "[bold reverse] CTRL+S: ENQUEUE [/]  [bold reverse] F4: SEND NOW [/]  [dim] ESC: CANCEL [/]",
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
        elif event.key == "f4":
            self.send_now()
            event.prevent_default()
            event.stop()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def _selected_template(self) -> Optional[tuple[str, str]]:
        """Returns (initiative, template_id) from the template picker, or
        None if nothing's selected."""
        template_raw = self.query_one("#followup_template", SearchSelect).value
        if not template_raw:
            return None
        if "::" in template_raw:
            initiative, template_id = template_raw.split("::", 1)
        else:
            initiative, template_id = "rta", template_raw
        return initiative, template_id

    def send_now(self) -> None:
        """Deliberately named without the "action_" prefix - see
        CallLogModal.send_followup_now()'s docstring for why (Textual
        auto-dispatches a Binding's action string to "action_<name>" AND
        handle_keys() above calls it directly; action_-prefixing this
        would fire both and send twice per keypress).

        Mark, 2026-10-09: "Can we still use 'f' to open the modal, but
        provide a send-now keymap on the modal?" - renders and sends the
        currently-selected template/recipient immediately via
        PersonalizedOutreachService.send_now() (the same macro Call Log's
        F4 uses), skipping the schedule-then-render-then-review pipeline
        this modal's Ctrl+S path still uses. Does not touch the follow-up
        queue at all - nothing is scheduled, nothing needs "preparing"
        afterward.
        """
        picked = self._selected_template()
        if picked is None:
            self.app.notify("Please select an email template", severity="error")
            return
        initiative, template_id = picked
        recipient_email = self.query_one("#followup_contact", SearchSelect).value
        self.run_worker(self._send_now_worker(template_id, initiative, recipient_email or None))

    async def _send_now_worker(
        self, template_id: str, initiative: str, recipient_email: Optional[str]
    ) -> None:
        import asyncio

        from cocli.application.email_service import EmailService
        from cocli.core.config import load_campaign_config
        from cocli.models.mail import EmailSettings

        campaign = get_campaign() or "default"

        def _send() -> tuple[int, int, Optional[str]]:
            service = PersonalizedOutreachService(campaign)
            raw = load_campaign_config(campaign) or {}
            email_raw = raw.get("email") or {}
            settings = EmailSettings.model_validate(email_raw)
            aws = raw.get("aws") or {}
            profile = aws.get("profile") if isinstance(aws.get("profile"), str) else None
            email_service = EmailService(campaign, settings, aws_profile=profile)

            try:
                result = service.send_now(
                    self.company_slug,
                    template_id=template_id,
                    initiative=initiative,
                    email_service=email_service,
                    recipient_email=recipient_email,
                )
            except ValueError as exc:
                return 0, 0, str(exc)
            return result.sent, result.failed, None

        try:
            sent, failed, error = await asyncio.to_thread(_send)
        except Exception as exc:
            self.app.notify(f"Send failed: {exc}", severity="error")
            return

        if error:
            self.app.notify(error, severity="error")
            return
        if failed:
            self.app.notify(
                f"Failed to send ({template_id}) to {self.company_slug}", severity="error"
            )
            return

        self.app.notify(f"Sent ({template_id}) to {self.company_name} now.")
        self.dismiss(True)

    def action_save(self) -> None:
        date_str = self.query_one("#followup_date", CocliInput).value.strip()
        try:
            scheduled_date = parse_follow_up_when(date_str)
        except ValueError:
            self.app.notify(f"Invalid date: '{date_str}'", severity="error")
            return

        picked = self._selected_template()
        if picked is None:
            self.app.notify("Please select an email template", severity="error")
            return
        initiative, template_id = picked

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
