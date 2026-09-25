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
    backend: Optional[str] = typer.Option(
        None, "--backend", help="Override email backend: ses, m365, m365_smtp, m365_graph."
    ),
) -> None:
    """Send one email via SES or M365 and record a note on the matching company."""
    campaign_name = _require_campaign()
    settings, profile = _settings(campaign_name)
    if backend:
        settings.backend = backend  # type: ignore[assignment]
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


@app.command("poll-events")
def poll_events(
    limit: int = typer.Option(10, "--limit", help="Max SQS messages to fetch (max 10 per call)."),
) -> None:
    """Poll the SQS queue for SES bounce/complaint events; record them and
    auto-suppress permanent bounces/complaints."""
    campaign_name = _require_campaign()
    settings, profile = _settings(campaign_name)
    from cocli.application.email_events_service import EmailEventsService

    service = EmailEventsService(campaign_name, region=settings.ses_region, profile=profile)
    try:
        result = service.poll(limit=limit)
    except Exception as exc:
        logger.error("Poll-events failed: %s", exc)
        raise typer.Exit(code=1) from exc
    logger.info(
        "Poll-events fetched=%s recorded=%s ignored=%s suppressed=%s",
        result.fetched,
        result.recorded,
        result.ignored,
        len(result.suppressed),
    )
    console.print(
        f"[green]Poll-events[/green] fetched={result.fetched} recorded={result.recorded} "
        f"ignored={result.ignored} suppressed={result.suppressed}"
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
    template: str = typer.Option(
        "email_01_pas_hook.md", "--template", "-t", help="Template filename."
    ),
    initiative: str = typer.Option(
        "rta", "--initiative", "-i", help="Which campaigns/<c>/initiatives/<name>/ this batch belongs to."
    ),
    tag: Optional[str] = typer.Option(
        None, "--tag", help="Filter prospects by tag (e.g. testimonial-target)."
    ),
) -> None:
    """Generate personalized outreach email drafts for testing (filters prospects with contact first names)."""
    campaign_name = _require_campaign()
    from cocli.application.personalized_outreach_service import PersonalizedOutreachService

    service = PersonalizedOutreachService(campaign_name)
    matches = service.find_eligible_prospects(
        limit=limit,
        template_name=template,
        initiative=initiative,
        tag=tag,
    )

    if not matches:
        console.print(f"[yellow]No eligible prospects with contact first names found in campaign '{campaign_name}'.[/yellow]")
        return

    console.print(f"[bold green]Prepared & rendered {len(matches)} personalized email drafts for '{campaign_name}':[/bold green]\n")
    for idx, match in enumerate(matches, 1):
        draft_path = service.render_and_save_draft(match, template_id=template, initiative=initiative)
        console.print(f"[bold cyan][{idx}] {match.company_name}[/bold cyan] ({match.company_slug})")
        console.print(f"    Recipient: {match.contact_name} <{match.recipient_email}> (First Name: [bold]{match.first_name}[/bold])")
        console.print(f"    Subject: {match.subject}")
        console.print(f"    Saved Draft: [dim]{draft_path}[/dim]")
        console.print(f"    Body Preview:\n{match.body[:200]}...\n")


@app.command("enqueue-followups")
def enqueue_followups(
    tag: str = typer.Option(..., "--tag", help="Company tag to select targets by (e.g. testimonial-target)."),
    template: str = typer.Option(..., "--template", "-t", help="Template filename (e.g. request_testimonial.md)."),
    initiative: str = typer.Option("rta", "--initiative", "-i", help="Initiative name (e.g. testimonials)."),
    render: bool = typer.Option(
        False, "--render", "-r", help="Immediately render and freeze due follow-ups into batch drafts."
    ),
) -> None:
    """Batch-enqueue email follow-ups for all companies matching a tag."""
    campaign_name = _require_campaign()
    from cocli.application.follow_up_service import FollowUpService

    service = FollowUpService(campaign_name)
    tasks = service.enqueue_by_tag(
        tag,
        template_id=template,
        initiative=initiative,
        format="email",
    )
    console.print(
        f"[bold green]Enqueued {len(tasks)} follow-up(s)[/bold green] for tag='{tag}' with [{initiative}] {template}."
    )
    if render:
        result = service.process_due()
        console.print(
            f"[bold green]Rendered {result.emails_queued} email draft(s) into Batch Email Drafts.[/bold green]"
        )
        if result.errors:
            for err in result.errors:
                console.print(f"[yellow]  - {err}[/yellow]")


@app.command("send-batch")
def send_batch(
    limit: int = typer.Option(10, "--limit", "-l", help="Number of prospects with contact first names to select."),
    template: str = typer.Option(
        "email_01_pas_hook.md", "--template", "-t", help="Template filename (see prepare-batch preview)."
    ),
    initiative: str = typer.Option(
        "rta", "--initiative", "-i", help="Which campaigns/<c>/initiatives/<name>/ this batch belongs to."
    ),
    bcc: list[str] = typer.Option(
        [], "--bcc", help="Bcc address(es) - repeatable. Applied to this send only, in addition to campaign config."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview the batch without sending or writing to the send log."
    ),
) -> None:
    """Actually send a batch via SES (prepare-batch only renders drafts)."""
    campaign_name = _require_campaign()
    from cocli.application.personalized_outreach_service import PersonalizedOutreachService

    service = PersonalizedOutreachService(campaign_name)
    matches = service.find_eligible_prospects(limit=limit, template_name=template, initiative=initiative)

    if not matches:
        console.print(f"[yellow]No eligible prospects with contact first names found in campaign '{campaign_name}'.[/yellow]")
        return

    if dry_run:
        console.print(f"[bold blue]Dry run[/bold blue] - would send {len(matches)} email(s) for '{campaign_name}':\n")
        for idx, match in enumerate(matches, 1):
            console.print(f"[bold cyan][{idx}] {match.company_name}[/bold cyan] ({match.company_slug})")
            console.print(f"    To: {match.contact_name} <{match.recipient_email}>")
            if bcc:
                console.print(f"    Bcc: {', '.join(bcc)}")
            console.print(f"    Subject: {match.subject}\n")
        return

    settings, profile = _settings(campaign_name)
    email_service = EmailService(campaign_name, settings, aws_profile=profile)
    result = service.send_batch(
        matches,
        template_id=template,
        email_service=email_service,
        initiative=initiative,
        bcc_addresses=bcc or None,
    )

    console.print(
        f"[bold green]Batch {result.batch_id}[/bold green]: "
        f"sent={result.sent} failed={result.failed}"
    )


@app.command("list-pending")
def list_pending() -> None:
    """List every not-yet-sent pending-batch row - the answer to "what's
    still queued to send." A row disappears from here the moment it's
    sent (send-pending/send-batch remove it from pending.usv and append
    a SendLogEntry to email-send-log/log.usv instead - that's the
    permanent "was this sent" record, queryable via `list_send_log()`)."""
    campaign_name = _require_campaign()
    from cocli.application.personalized_outreach_service import PersonalizedOutreachService

    service = PersonalizedOutreachService(campaign_name)
    entries = service.list_pending_batches()

    if not entries:
        console.print("[dim]Nothing pending - everything queued has been sent or discarded.[/dim]")
        return

    for entry in entries:
        console.print(
            f"[bold cyan]{entry.batch_id}[/bold cyan]  {entry.company_slug} <{entry.recipient}>  "
            f"({entry.template_id}, {entry.initiative})"
        )


@app.command("send-pending")
def send_pending(
    company_slug: Optional[str] = typer.Argument(
        None, help="Company slug to send the pending entry for (omit if using --all)."
    ),
    batch_id: Optional[str] = typer.Option(
        None, "--batch-id", "-b", help="Disambiguate if more than one pending entry matches this company."
    ),
    cc: list[str] = typer.Option(
        [], "--cc", help="Cc address(es) - repeatable. Applied to this send only, not saved anywhere."
    ),
    bcc: list[str] = typer.Option(
        [], "--bcc", help="Bcc address(es) - repeatable. Applied to this send only, in addition to campaign config."
    ),
    all_pending: bool = typer.Option(
        False, "--all", "-a", help="Send all pending draft entries across all batches."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be sent without actually sending."
    ),
) -> None:
    """Send exactly one pending entry as a one-off or all pending entries (--all)."""
    campaign_name = _require_campaign()
    from cocli.application.personalized_outreach_service import PersonalizedOutreachService

    service = PersonalizedOutreachService(campaign_name)

    if all_pending:
        entries = service.list_pending_batches()
        if not entries:
            console.print("[dim]Nothing pending - everything queued has been sent or discarded.[/dim]")
            return
        if dry_run:
            console.print(f"[bold blue]Dry run[/bold blue] - would send {len(entries)} pending email(s):")
            for e in entries:
                match = service.entry_to_match(e)
                console.print(f"  {e.company_slug} <{e.recipient}>: {match.subject}")
                if cc:
                    console.print(f"    Cc: {', '.join(cc)}")
                if bcc:
                    console.print(f"    Bcc: {', '.join(bcc)}")
            return

        settings, profile = _settings(campaign_name)
        email_service = EmailService(campaign_name, settings, aws_profile=profile)
        total_sent = 0
        total_failed = 0
        for entry in entries:
            res = service.send_one_pending_entry(
                entry.batch_id,
                entry.company_slug,
                email_service=email_service,
                cc_addresses=cc or None,
                bcc_addresses=bcc or None,
            )
            total_sent += res.sent
            total_failed += res.failed
            console.print(
                f"[bold green]Sent to {entry.recipient}[/bold green] ({entry.company_slug}): "
                f"sent={res.sent} failed={res.failed}"
            )
        console.print(f"[bold]Completed:[/bold] sent={total_sent} failed={total_failed}")
        return

    if not company_slug:
        console.print("[bold red]Must provide company_slug or use --all.[/bold red]")
        raise typer.Exit(code=1)

    matches = [e for e in service.list_pending_batches() if e.company_slug == company_slug]
    if batch_id:
        matches = [e for e in matches if e.batch_id == batch_id]

    if not matches:
        console.print(f"[bold red]No pending entry found for '{company_slug}'.[/bold red]")
        raise typer.Exit(code=1)
    if len(matches) > 1:
        console.print(
            f"[bold red]{len(matches)} pending entries match '{company_slug}' - pass --batch-id to pick one:[/bold red]"
        )
        for entry in matches:
            console.print(f"  {entry.batch_id}  ({entry.template_id})")
        raise typer.Exit(code=1)

    entry = matches[0]
    if dry_run:
        match = service.entry_to_match(entry)
        console.print(f"[bold blue]Dry run[/bold blue] - would send to {entry.recipient}")
        if cc:
            console.print(f"    Cc: {', '.join(cc)}")
        if bcc:
            console.print(f"    Bcc: {', '.join(bcc)}")
        console.print(f"    Subject: {match.subject}")
        return

    settings, profile = _settings(campaign_name)
    email_service = EmailService(campaign_name, settings, aws_profile=profile)
    result = service.send_one_pending_entry(
        entry.batch_id,
        entry.company_slug,
        email_service=email_service,
        cc_addresses=cc or None,
        bcc_addresses=bcc or None,
    )

    console.print(
        f"[bold green]Sent to {entry.recipient}[/bold green]: sent={result.sent} failed={result.failed}"
    )


@app.command("render-html-preview")
def render_html_preview(
    company_slug: str = typer.Argument(..., help="Company slug (matches rendered-outreach/<slug>/)."),
    template: str = typer.Argument(..., help="Template filename, e.g. email_02_product_overview.md."),
    initiative: str = typer.Option(
        "rta", "--initiative", "-i", help="Which campaigns/<c>/initiatives/<name>/ this belongs to."
    ),
    open_it: bool = typer.Option(
        True, "--open/--no-open", help="Open the rendered HTML in the desktop browser after regenerating it."
    ),
) -> None:
    """Regenerate rendered-outreach/<slug>/<template>.html from the
    *current* content of the sibling .md file - the actual HTML that
    would be sent, so you can review the real image/testimonial/button
    rendering, not just markdown source with raw HTML tags in it. Only
    produces output for templates with a `layout:` frontmatter key; a
    plain-text template has nothing beyond the body already visible in
    the .md file."""
    campaign_name = _require_campaign()
    from cocli.application.personalized_outreach_service import PersonalizedOutreachService
    from cocli.utils.open_url import open_url

    service = PersonalizedOutreachService(campaign_name)
    html_path = service.render_and_save_html_preview(initiative, company_slug, template)

    if html_path is None:
        console.print(
            "[yellow]No HTML preview produced - either no rendered-outreach draft exists yet "
            f"for '{company_slug}'/{template}, or that template has no `layout:` key.[/yellow]"
        )
        raise typer.Exit(code=1)

    console.print(f"[bold green]Rendered:[/bold green] {html_path}")
    if open_it:
        if not open_url(str(html_path)):
            console.print("[yellow]Could not open a browser - open the path above manually.[/yellow]")


@app.command("enqueue-initiative")
def enqueue_initiative_command(
    initiative: str = typer.Argument(..., help="Initiative name (e.g. testimonials, rta)."),
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name. Defaults to active campaign."
    ),
    render: bool = typer.Option(
        True, "--render/--no-render", help="Render email drafts immediately."
    ),
    template: Optional[str] = typer.Option(
        None, "--template", "-t", help="Override initiative default template."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Simulate without writing files."
    ),
) -> None:
    """Enqueue follow-up tasks for an initiative based on its declarative manifest (initiative.yaml)."""
    campaign_name = campaign or _require_campaign()
    from cocli.application.follow_up_service import FollowUpService

    service = FollowUpService(campaign_name)
    try:
        result = service.enqueue_initiative(
            initiative,
            template_id=template,
            render=render,
            dry_run=dry_run,
        )
    except Exception as exc:
        logger.error("Failed to enqueue initiative '%s': %s", initiative, exc)
        console.print(f"[bold red]Failed to enqueue initiative '{initiative}':[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    if dry_run:
        console.print(
            f"[bold blue]Dry run:[/bold blue] would enqueue {result.enqueued} target(s) for initiative '{initiative}'."
        )
    else:
        console.print(
            f"[bold green]Enqueued:[/bold green] {result.enqueued} target(s), "
            f"[bold green]rendered:[/bold green] {result.rendered} draft(s) for initiative '{initiative}'."
        )
        if result.errors:
            for err in result.errors:
                console.print(f"[bold yellow]Warning:[/bold yellow] {err}")



