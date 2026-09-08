"""Compose/send (and reply) from company context. Uses EmailService + SES."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from textual import events, on, work
from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Label, Static, TextArea

from cocli.application.email_service import Boto3SesSender, EmailService, SesSender
from cocli.core.config import get_campaign, load_campaign_config
from cocli.models.mail import EmailSettings, SendMailRequest, SendMailResult
from cocli.utils.utm import append_utm_params

from .inputs import CocliInput


class EmailComposeModal(ModalScreen[bool]):
    BINDINGS = [
        ("escape", "dismiss(False)", "Cancel"),
        ("ctrl+s", "send_mail", "Send"),
        ("ctrl+enter", "send_mail", "Send"),
        ("ctrl+j", "send_mail", "Send"),
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
        self._sending = False
        self._campaign = get_campaign()
        raw = load_campaign_config(self._campaign) if self._campaign else None
        raw = raw or {}
        self._settings = EmailSettings.model_validate(raw.get("email") or {})
        aws = raw.get("aws") or {}
        self._aws_profile = aws.get("profile") if isinstance(aws.get("profile"), str) else None
        self._from_address = self._settings.from_address or ""
        self._ses_sender: Optional[SesSender] = None
        self._body = append_utm_params(
            body,
            campaign=self._campaign,
            company_slug=self.company_slug,
            source="email_sequence",
            medium="email",
        )

    def compose(self) -> ComposeResult:
        from_line = self._from_address or "(set campaign [email].from_address)"
        with Container(id="email-compose-form"):
            yield Label(f"EMAIL: [bold cyan]{self.company_slug}[/]", id="email-compose-title")
            yield Label(f"From: {from_line}", id="email-from")
            yield Label("To", classes="field-label")
            yield CocliInput(value=self._to, id="email-to", placeholder="you@example.com")
            yield Label("Subject", classes="field-label")
            yield CocliInput(value=self._subject, id="email-subject")
            yield Label("Body  (Ctrl+S / Ctrl+Enter / Ctrl+J send)", classes="field-label")
            yield TextArea(self._body, id="email-body")
            yield Static(
                "[bold reverse] CTRL+S / CTRL+ENTER / CTRL+J: SEND [/]  [dim] ESC: CANCEL [/]",
                id="email-compose-help",
            )

    def on_mount(self) -> None:
        target = (
            self.query_one("#email-body", TextArea)
            if self._to and self._subject
            else self.query_one("#email-to", CocliInput)
        )
        target.focus()
        # 1Password/Hello for the SES profile happens here, not on Ctrl+S,
        # so send can dismiss the modal without a second keypress.
        self._warm_ses_sender()

    @work(exclusive=True, thread=True)
    def _warm_ses_sender(self) -> None:
        if self._ses_sender is not None:
            return
        try:
            sender = Boto3SesSender(
                self._settings.ses_region,
                profile=self._aws_profile,
                configuration_set=self._settings.ses_configuration_set,
            )
            sender._reply_to = self._settings.reply_to
            self._ses_sender = sender
        except Exception as exc:  # noqa: BLE001
            message = f"SES session: {exc}"

            def _warn() -> None:
                self.app.notify(message, severity="warning")

            self.app.call_from_thread(_warn)

    @on(events.Key)
    def handle_keys(self, event: events.Key) -> None:
        # TextArea swallows the screen binding; CallLogModal uses the same pattern.
        if event.key in ("ctrl+s", "ctrl+enter", "ctrl+j"):
            event.stop()
            event.prevent_default()
            self.run_worker(self._send_mail())

    def action_send_mail(self) -> None:
        self.run_worker(self._send_mail())

    async def _send_mail(self) -> None:
        if self._sending:
            return
        to_address = self.query_one("#email-to", CocliInput).value.strip()
        subject = self.query_one("#email-subject", CocliInput).value.strip()
        raw_body = self.query_one("#email-body", TextArea).text.strip()
        body = append_utm_params(
            raw_body,
            campaign=self._campaign,
            company_slug=self.company_slug,
            source="email_sequence",
            medium="email",
        )

        if not to_address or not subject or not body:
            self.app.notify("To, subject, and body are required", severity="warning")
            return
        if not self._campaign:
            self.app.notify("No campaign set", severity="error")
            return
        if not self._from_address:
            self.app.notify("campaign [email].from_address is not set", severity="error")
            return
        self._sending = True
        self.app.notify(f"Sending from {self._from_address}...")
        try:
            result = await asyncio.to_thread(
                self._do_send, to_address, subject, body
            )
        except Exception as exc:  # noqa: BLE001
            self._sending = False
            self.app.notify(f"Send failed: {exc}", severity="error")
            return
        self.app.notify(f"Sent {result.to_address}")
        self.dismiss(True)

    def _do_send(self, to_address: str, subject: str, body: str) -> SendMailResult:
        if not self._campaign:
            raise ValueError("No campaign set")
        service = EmailService(
            self._campaign,
            self._settings,
            ses_sender=self._ses_sender,
            aws_profile=self._aws_profile,
        )
        return service.send(
            SendMailRequest(
                to_address=to_address,
                subject=subject,
                body=body,
                company_slug=self.company_slug,
            )
        )
