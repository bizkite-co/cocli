"""CLI adapters for SES send and IMAP monitor."""

from __future__ import annotations

import logging
from typing import Optional

import typer
from rich.console import Console

from cocli.application.email_service import EmailService
from cocli.core.config import get_campaign, load_campaign_config
from cocli.models.mail import EmailSettings, SendMailRequest

logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer(
    help="Send via SES and poll a configured IMAP inbox into company notes. Not a mail client.",
    no_args_is_help=True,
)


def _require_campaign() -> str:
    name = get_campaign()
    if not name:
        logger.error("No campaign set. Pass --campaign or set COCLI_CAMPAIGN.")
        raise typer.Exit(code=1)
    return name


def _settings(campaign_name: str) -> tuple[EmailSettings, Optional[str]]:
    raw = load_campaign_config(campaign_name) or {}
    email_raw = raw.get("email") or {}
    settings = EmailSettings.model_validate(email_raw)
    aws = raw.get("aws") or {}
    profile = aws.get("profile")
    return settings, profile if isinstance(profile, str) else None


@app.command("send")
def send_mail(
    to_address: str = typer.Option(..., "--to", help="Recipient email address."),
    subject: str = typer.Option(..., "--subject", help="Subject line."),
    body: str = typer.Option(..., "--body", help="Plain-text body."),
    company: Optional[str] = typer.Option(
        None, "--company", help="Company slug for the CRM note. Looked up from --to if omitted."
    ),
    from_address: Optional[str] = typer.Option(
        None, "--from", help="Override campaign [email].from_address."
    ),
) -> None:
    """Send one email via SES and record a note on the matching company."""
    campaign_name = _require_campaign()
    settings, profile = _settings(campaign_name)
    service = EmailService(campaign_name, settings, aws_profile=profile)
    try:
        result = service.send(
            SendMailRequest(
                to_address=to_address,
                subject=subject,
                body=body,
                company_slug=company,
                from_address=from_address,
            )
        )
    except Exception as exc:
        logger.error("Send failed: %s", exc)
        raise typer.Exit(code=1) from exc
    logger.info(
        "Sent message_id=%s to=%s note=%s company=%s",
        result.message_id,
        result.to_address,
        result.note_written,
        result.company_slug,
    )
    console.print(
        f"[green]Sent[/green] {result.to_address} "
        f"message_id={result.message_id} note={result.note_written} "
        f"company={result.company_slug}"
    )


@app.command("poll")
def poll_mail(
    limit: int = typer.Option(50, "--limit", help="Max UNSEEN messages to fetch per folder."),
) -> None:
    """Poll configured IMAP folders and write notes for messages that match a company."""
    campaign_name = _require_campaign()
    settings, profile = _settings(campaign_name)
    service = EmailService(campaign_name, settings, aws_profile=profile)
    try:
        result = service.poll(limit=limit)
    except Exception as exc:
        logger.error("Poll failed: %s", exc)
        raise typer.Exit(code=1) from exc
    logger.info(
        "Poll fetched=%s noted=%s skipped_seen=%s unmatched=%s",
        result.fetched,
        result.noted,
        result.skipped_seen,
        result.unmatched,
    )
    console.print(
        f"[green]Poll[/green] fetched={result.fetched} noted={result.noted} "
        f"skipped_seen={result.skipped_seen} unmatched={result.unmatched}"
    )
