"""Interactive outreach email modal with pre-populated copy and live call conversation context."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Label, Static, TextArea

from cocli.application.call_history_service import (
    ConnectedCallInfo,
    find_recent_connected_call,
    format_call_opener,
    format_call_subject,
)
from cocli.application.email_service import EmailService
from cocli.application.personalized_outreach_service import (
    PersonalizedOutreachService,
    extract_first_name,
)
from cocli.core.config import get_campaign, load_campaign_config
from cocli.models.mail import EmailSettings
from .inputs import CocliInput

logger = logging.getLogger(__name__)


class EmailSendModal(ModalScreen[bool]):
    """A spacious modal for reviewing, customizing, and sending templated outreach emails.

    Pre-populates subject and body with personalized merge fields, UTM links,
    and prior phone conversation context (e.g. 'Following up on our talk on 10/14')
    to defeat cold-blast spam screening.
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+s", "send_mail", "Send Now"),
        ("ctrl+enter", "send_mail", "Send Now"),
        ("f4", "send_mail", "Send Now"),
    ]

    DEFAULT_CSS = """
    EmailSendModal {
        align: center middle;
    }
    #email-send-form {
        width: 86;
        height: auto;
        max-height: 92%;
        background: #111111;
        border: double #00ff00;
        padding: 1 2;
    }
    #email-send-form CocliInput {
        width: 100%;
        margin-bottom: 1;
        border: tall #333333;
    }
    #email-send-form CocliInput:focus {
        border: tall #00ff00;
    }
    #email-send-body {
        height: 16;
        margin-bottom: 1;
        border: tall #333333;
    }
    #email-send-body:focus {
        border: tall #00ff00;
    }
    .field-label {
        color: #888888;
        margin-bottom: 0;
    }
    .call-context-box {
        margin-bottom: 1;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        company_slug: str,
        company_name: Optional[str] = None,
        recipient_email: Optional[str] = None,
        contact_name: Optional[str] = None,
        template_id: str = "request_testimonial.md",
        initiative: str = "testimonials",
        subject: Optional[str] = None,
        body: Optional[str] = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.company_slug = company_slug
        self.company_name = company_name or company_slug.replace("-", " ").title()
        self.recipient_email = recipient_email
        self.contact_name = contact_name
        self.template_id = template_id
        self.initiative = initiative
        self._initial_subject = subject
        self._initial_body = body
        self._campaign = get_campaign() or "default"
        self._sending = False

        # Find prior live conversation from call history
        self.call_info: Optional[ConnectedCallInfo] = find_recent_connected_call(
            company_slug=self.company_slug,
            contact_name=self.contact_name,
            recipient_email=self.recipient_email,
        )

        # Pre-render copy if not supplied
        if self._initial_subject is None or self._initial_body is None:
            self._prepare_initial_copy()

    def _prepare_initial_copy(self) -> None:
        import re

        service = PersonalizedOutreachService(self._campaign)
        match = service.find_contact_for_company(
            self.company_slug, recipient_email=self.recipient_email
        )

        first_name = ""
        person_slug = None
        if match:
            first_name = match.first_name
            person_slug = match.person_slug
            if not self.recipient_email:
                self.recipient_email = match.recipient_email
            if not self.contact_name:
                self.contact_name = match.contact_name

        if self.contact_name:
            extracted = extract_first_name(self.contact_name)
            if extracted:
                first_name = extracted

        gen_subject, gen_body = service.generate_copy(
            first_name=first_name or "there",
            company_name=self.company_name,
            company_slug=self.company_slug,
            template_name=self.template_id,
            initiative=self.initiative,
            person_slug=person_slug,
            full_name=self.contact_name,
        )

        # If a prior conversation occurred, incorporate conversational follow-up
        if self.call_info:
            gen_subject = format_call_subject(gen_subject, self.call_info, first_name=first_name)
            # Prepend conversational hook if template starts with standard greeting
            greet_match = re.match(r"^Hi\s+[^,]+,", gen_body)
            if greet_match:
                rest_of_body = gen_body[greet_match.end() :].lstrip()
                call_opener = format_call_opener(first_name, self.call_info)
                gen_body = f"{call_opener}\n\n{rest_of_body}"
            else:
                call_opener = format_call_opener(first_name, self.call_info)
                gen_body = f"{call_opener}\n\n{gen_body}"

        self._initial_subject = self._initial_subject or gen_subject
        self._initial_body = self._initial_body or gen_body

    def compose(self) -> ComposeResult:
        contact_display = (
            f"{self.contact_name} <{self.recipient_email}>"
            if self.contact_name and self.recipient_email
            else self.recipient_email or "(no email)"
        )

        with Container(id="email-send-form"):
            yield Label(
                f"EDIT & SEND OUTREACH: [bold cyan]{self.company_name}[/]",
                id="email-send-title",
            )
            yield Label(
                f"To: [bold yellow]{contact_display}[/]   Template: [dim][{self.initiative}] {self.template_id}[/]",
                classes="modal-subtitle",
            )

            # Connected call context banner
            if self.call_info:
                call_text = (
                    f"📞 [bold green]Spoke on {self.call_info.call_date_str}:[/] "
                    f"[dim]{self.call_info.notes_snippet}[/]"
                )
            else:
                call_text = "[dim]📞 No recent connected call on file (cold outreach)[/dim]"
            yield Static(call_text, classes="call-context-box")

            yield Label("Subject", classes="field-label")
            yield CocliInput(value=self._initial_subject or "", id="email-send-subject")

            yield Label("Body (Markdown / HTML layout with UTM tracking)", classes="field-label")
            yield TextArea(self._initial_body or "", id="email-send-body")

            yield Static(
                "[bold reverse] CTRL+S / F4: SEND NOW [/]  [dim] ESC: CANCEL [/]",
                id="email-send-help",
            )

    def on_mount(self) -> None:
        self.query_one("#email-send-body", TextArea).focus()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_send_mail(self) -> None:
        if self._sending:
            return
        subject = self.query_one("#email-send-subject", CocliInput).value.strip()
        body = self.query_one("#email-send-body", TextArea).text.strip()

        if not subject:
            self.app.notify("Subject cannot be empty", severity="error")
            return
        if not body:
            self.app.notify("Body cannot be empty", severity="error")
            return

        self._sending = True
        self.app.notify(f"Sending ({self.template_id}) to {self.recipient_email or self.company_slug}...")
        self.run_worker(self._send_worker(subject, body))

    async def _send_worker(self, subject: str, body: str) -> None:
        raw = load_campaign_config(self._campaign) or {}
        email_raw = raw.get("email") or {}
        settings = EmailSettings.model_validate(email_raw)
        aws = raw.get("aws") or {}
        profile = aws.get("profile") if isinstance(aws.get("profile"), str) else None
        email_service = EmailService(self._campaign, settings, aws_profile=profile)

        def _send() -> tuple[int, int, Optional[str]]:
            service = PersonalizedOutreachService(self._campaign)
            try:
                result = service.send_now(
                    self.company_slug,
                    template_id=self.template_id,
                    initiative=self.initiative,
                    email_service=email_service,
                    recipient_email=self.recipient_email,
                    subject=subject,
                    body=body,
                )
            except Exception as exc:
                return 0, 0, str(exc)
            return result.sent, result.failed, None

        try:
            sent, failed, error = await asyncio.to_thread(_send)
        except Exception as exc:
            self._sending = False
            self.app.notify(f"Send failed: {exc}", severity="error")
            return

        self._sending = False
        if error:
            self.app.notify(error, severity="error")
            return
        if failed:
            self.app.notify(
                f"Failed to send to {self.recipient_email or self.company_slug}",
                severity="error",
            )
            return

        self.app.notify(f"Sent ({self.template_id}) to {self.company_name} now.")
        self.dismiss(True)
