"""CLI adapters for SES send and IMAP monitor."""

from __future__ import annotations

import logging
from typing import Optional

import typer
from rich.console import Console

from cocli.application.email_service import EmailService
from cocli.application.mail_oauth import authorize_public_client, build_authorize_url
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


@app.command("authorize")
def authorize_mail() -> None:
    """Browser OAuth for the campaign IMAP user. Writes the local token cache (no mutt-setup)."""
    campaign_name = _require_campaign()
    settings, _profile = _settings(campaign_name)
    try:
        console.print("Open this URL (GoDaddy 2FA may apply):")
        console.print(build_authorize_url(settings))
        path = authorize_public_client(settings)
    except Exception as exc:
        logger.error("Authorize failed: %s", exc)
        raise typer.Exit(code=1) from exc
    console.print(f"[green]Authorized[/green] {settings.imap_user} cache={path}")


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
    """Poll IMAP for UNSEEN mail from monitored addresses; file notes; ntfy if any match."""
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


@app.command("unsubscribe")
def unsubscribe(
    address: str = typer.Option(..., "--address", "-a", help="Email address to unsubscribe and suppress."),
    reason: str = typer.Option("COMPLAINT", "--reason", "-r", help="Reason: COMPLAINT or BOUNCE."),
) -> None:
    """Unsubscribe an email address, adding to AWS SES suppression list and local exclusions."""
    campaign_name = _require_campaign()
    _, profile = _settings(campaign_name)

    from cocli.core.exclusions import ExclusionManager
    from cocli.application.ses_suppression_service import SesSuppressionService

    ex_mgr = ExclusionManager(campaign_name)
    ex_mgr.add_exclusion(domain=address, reason=f"unsubscribe:{reason}")

    ses_suppress = SesSuppressionService(profile=profile)
    ses_success = ses_suppress.suppress_email(address, reason=reason)

    console.print(
        f"[bold green]Unsubscribed[/bold green] {address}. "
        f"Local exclusion added. AWS SES suppression: {'[green]Success[/green]' if ses_success else '[yellow]Failed/Offline[/yellow]'}"
    )


@app.command("suppression-list")
def list_suppressed(
    limit: int = typer.Option(50, "--limit", help="Max suppressed emails to display."),
) -> None:
    """List suppressed email addresses from AWS SES account-level suppression list."""
    campaign_name = _require_campaign()
    _, profile = _settings(campaign_name)

    from cocli.application.ses_suppression_service import SesSuppressionService

    ses_suppress = SesSuppressionService(profile=profile)
    items = ses_suppress.list_suppressed(limit=limit)

    if not items:
        console.print("[dim]No suppressed destinations found in AWS SES.[/dim]")
        return

    for item in items:
        console.print(f"[cyan]{item['email']}[/cyan] ({item['reason']}) - updated: {item['last_updated']}")


@app.command("prepare-batch")
def prepare_batch(
    limit: int = typer.Option(10, "--limit", "-l", help="Number of prospects with contact first names to select."),
) -> None:
    """Generate personalized outreach email drafts for testing (filters prospects with contact first names)."""
    campaign_name = _require_campaign()
    from cocli.application.personalized_outreach_service import PersonalizedOutreachService

    service = PersonalizedOutreachService(campaign_name)
    matches = service.find_eligible_prospects(limit=limit)

    if not matches:
        console.print(f"[yellow]No eligible prospects with contact first names found in campaign '{campaign_name}'.[/yellow]")
        return

    console.print(f"[bold green]Prepared & rendered {len(matches)} personalized email drafts for '{campaign_name}':[/bold green]\n")
    for idx, match in enumerate(matches, 1):
        draft_path = service.render_and_save_draft(match)
        console.print(f"[bold cyan][{idx}] {match.company_name}[/bold cyan] ({match.company_slug})")
        console.print(f"    Recipient: {match.contact_name} <{match.recipient_email}> (First Name: [bold]{match.first_name}[/bold])")
        console.print(f"    Subject: {match.subject}")
        console.print(f"    Saved Draft: [dim]{draft_path}[/dim]")
        console.print(f"    Body Preview:\n{match.body[:200]}...\n")



