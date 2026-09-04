"""Compose/send (and reply) from company context. Uses EmailService + SES."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Label, Static, TextArea

from cocli.application.email_service import EmailService
from cocli.core.config import get_campaign, load_campaign_config
from cocli.models.mail import EmailSettings, SendMailRequest
from .inputs import CocliInput


class EmailComposeModal(ModalScreen[bool]):
    BINDINGS = [
        ("escape", "dismiss(False)", "Cancel"),
        ("ctrl+s", "send_mail", "Send"),
    ]

    DEFAULT_CSS = """
    EmailComposeModal {
        align: center middle;
    }
    #email-compose-form {
        width: 72;
        height: auto;
        max-height: 90%;
        background: #111111;
        border: double #00ff00;
        padding: 1 2;
    }
    #email-compose-form CocliInput {
        width: 100%;
        margin-bottom: 1;
        border: tall #333333;
    }
    #email-compose-form CocliInput:focus {
        border: tall #00ff00;
    }
    #email-body {
        height: 12;
        margin-bottom: 1;
        border: tall #333333;
    }
    #email-body:focus {
        border: tall #00ff00;
    }
    """

    def __init__(
        self,
        company_slug: str,
        to_address: str = "",
        subject: str = "",
        body: str = "",
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.company_slug = company_slug
        self._to = to_address
        self._subject = subject
        self._body = body

    def compose(self) -> ComposeResult:
        with Container(id="email-compose-form"):
            yield Label(f"EMAIL: [bold cyan]{self.company_slug}[/]", id="email-compose-title")
            yield Label("To", classes="field-label")
            yield CocliInput(value=self._to, id="email-to", placeholder="client@example.com")
            yield Label("Subject", classes="field-label")
            yield CocliInput(value=self._subject, id="email-subject")
            yield Label("Body  (Ctrl+S send)", classes="field-label")
            yield TextArea(self._body, id="email-body")
            yield Static("[bold reverse] CTRL+S: SEND [/]  [dim] ESC: CANCEL [/]", id="email-compose-help")

    def on_mount(self) -> None:
        target = (
            self.query_one("#email-body", TextArea)
            if self._to and self._subject
            else self.query_one("#email-to", CocliInput)
        )
        target.focus()

    def action_send_mail(self) -> None:
        to_address = self.query_one("#email-to", CocliInput).value.strip()
        subject = self.query_one("#email-subject", CocliInput).value.strip()
        body = self.query_one("#email-body", TextArea).text.strip()
        if not to_address or not subject or not body:
            self.app.notify("To, subject, and body are required", severity="warning")
            return
        campaign = get_campaign()
        if not campaign:
            self.app.notify("No campaign set", severity="error")
            return
        raw = load_campaign_config(campaign) or {}
        settings = EmailSettings.model_validate(raw.get("email") or {})
        aws = raw.get("aws") or {}
        profile = aws.get("profile") if isinstance(aws.get("profile"), str) else None
        service = EmailService(campaign, settings, aws_profile=profile)
        try:
            result = service.send(
                SendMailRequest(
                    to_address=to_address,
                    subject=subject,
                    body=body,
                    company_slug=self.company_slug,
                )
            )
        except Exception as exc:
            self.app.notify(f"Send failed: {exc}", severity="error")
            return
        self.app.notify(f"Sent {result.to_address}")
        self.dismiss(True)
