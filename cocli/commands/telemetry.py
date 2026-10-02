from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

import typer

def _get_wizard_cmds() -> tuple[Any, Any, Any, Any]:
    try:
        from gtm_telemetry_wizard.cli import sync_cmd, verify_cmd, wizard_cmd, ping_cmd
        return sync_cmd, verify_cmd, wizard_cmd, ping_cmd
    except ImportError:
        typer.echo("Error: gtm_telemetry_wizard package is not installed.", err=True)
        raise typer.Exit(code=1)
from cocli.application.engagement_service import EngagementService
from cocli.core.config import get_campaign

app = typer.Typer(no_args_is_help=True, help="Telemetry and web landing page signal ingestion.")
logger = logging.getLogger(__name__)


@app.command(name="ingest")
def ingest(
    json_data: Optional[str] = typer.Option(
        None, "--json", "-j", help="JSON string containing telemetry payload"
    ),
    file_path: Optional[Path] = typer.Option(
        None, "--file", "-f", help="Path to JSON file containing telemetry payload"
    ),
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name override"
    ),
) -> None:
    """Ingest web landing page (GTM/UTM) telemetry events into campaign engagement log."""
    camp = campaign or get_campaign() or "default"
    if not json_data and not file_path:
        typer.echo("Error: Either --json or --file must be specified.", err=True)
        raise typer.Exit(code=1)

    payload: dict[str, Any] = {}
    if file_path:
        if not file_path.is_file():
            typer.echo(f"Error: File not found: {file_path}", err=True)
            raise typer.Exit(code=1)
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    elif json_data:
        payload = json.loads(json_data)

    service = EngagementService(camp)
    event = service.ingest_telemetry(payload)
    typer.echo(
        f"Ingested telemetry event '{event.event_type}' for '{event.company_slug or 'unknown'}' in campaign '{camp}'."
    )


@app.command(name="sync")
def sync_telemetry(
    measurement_id: Optional[str] = typer.Option(
        None, "--measurement-id", "-m", help="Explicit GA4 Measurement ID override (e.g. G-XXXXXXXXXX)"
    ),
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name override"
    ),
    domain: str = typer.Option(
        "getretirementtaxanalyzer.com", "--domain", "-d", help="Target website domain"
    ),
) -> None:
    """Resolve/create GA4 Measurement ID and compile declarative GTM IaC container spec."""
    sync_cmd, _, _, _ = _get_wizard_cmds()
    sync_cmd(domain=domain, measurement_id=measurement_id)


@app.command(name="verify")
def verify_telemetry(
    url: str = typer.Option(
        "https://getretirementtaxanalyzer.com/?utm_source=email_sequence&utm_medium=email",
        "--url",
        "-u",
        help="Target webpage URL to test with Playwright",
    ),
) -> None:
    """Run Playwright E2E verification test against live URL to inspect dataLayer and network telemetry."""
    _, verify_cmd, _, _ = _get_wizard_cmds()
    verify_cmd(url=url)


@app.command(name="ping")
def ping_telemetry(
    measurement_id: str = typer.Option("G-HJJ9TK2TKY", "--measurement-id", "-m", help="Target GA4 Measurement ID"),
    domain: str = typer.Option("getretirementtaxanalyzer.com", "--domain", "-d", help="Target website domain"),
) -> None:
    """Send an initial telemetry hit to GA4 to warm up data ingestion and clear 48-hour missing traffic alerts."""
    _, _, _, ping_cmd = _get_wizard_cmds()
    ping_cmd(measurement_id=measurement_id, domain=domain)


@app.command(name="deploy")
def deploy_telemetry(
    container_id: str = typer.Option("GTM-53F6J2WX", "--container-id", "-c", help="Target GTM Container ID"),
    mode: str = typer.Option("api", "--mode", "-m", help="Deployment mode: 'api' (REST API v2) or 'browser' (Playwright)"),
    headful: bool = typer.Option(True, "--headful/--headless", help="Run browser visibly when using browser mode"),
) -> None:
    """Deploy GTM container IaC manifest via Google Tag Manager REST API v2 or browser automation."""
    from cocli.application.telemetry_service import GoogleTelemetryProvider
    from cocli.core.paths import paths
    from rich.console import Console

    console = Console()
    provider = GoogleTelemetryProvider()
    manifest_path = paths.campaigns / "roadmap" / "initiatives" / "rta" / "tracking" / "gtm-container-compiled.json"

    if not manifest_path.exists():
        console.print(f"[yellow]Compiled manifest not found at {manifest_path}. Running sync...[/yellow]")
        provider.compile_container_manifest("G-HJJ9TK2TKY", "roadmap")

    console.print(f"[bold green]Deploying GTM Container Manifest ({mode.upper()} mode):[/bold green] [dim]{manifest_path}[/dim]")

    if mode.lower() == "api":
        res = provider.deploy_gtm_via_api(manifest_path, container_id=container_id)
        if res.get("success"):
            console.print(f"[bold green]GTM REST API v2 Deployment Successful:[/bold green] {res.get('message')}")
        else:
            console.print(f"[bold yellow]REST API Deployment Note:[/bold yellow] {res.get('error')}")
            console.print("[dim]Tip: Authenticate gcloud (`gcloud auth login`) or set COCLI_GTM_ACCESS_TOKEN for REST API deployments.[/dim]")
    else:
        provider.deploy_gtm_container_automated(manifest_path, container_id=container_id, headful=headful)
        console.print("[bold green]Browser-based container import complete.[/bold green]")


@app.command(name="wizard")
def wizard_telemetry(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name override"),
    domain: str = typer.Option("getretirementtaxanalyzer.com", "--domain", "-d", help="Target website domain"),
    container_id: str = typer.Option("GTM-53F6J2WX", "--container-id", help="Target GTM Container ID"),
    ga4_id: str = typer.Option("G-HJJ9TK2TKY", "--ga4-id", "-g", help="Target GA4 Measurement ID"),
    skip_verify: bool = typer.Option(False, "--skip-verify", help="Skip Playwright live URL verification"),
) -> None:
    """Guided wizard for inspecting status, syncing IaC spec, verifying live site, and deploying GTM across Google accounts."""
    _, _, wizard_cmd, _ = _get_wizard_cmds()
    wizard_cmd(domain=domain, container_id=container_id, ga4_id=ga4_id, config=None, skip_verify=skip_verify)


@app.command(name="query")
def query_telemetry(
    property_id: Optional[str] = typer.Option(
        None, "--property-id", "-p", help="Google Analytics 4 Property ID (e.g. 555090946)"
    ),
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name filter"
    ),
    path: Optional[str] = typer.Option(
        None, "--path", help="Page path filter"
    ),
    days: int = typer.Option(
        7, "--days", "-d", help="Days of history to query"
    ),
    realtime: bool = typer.Option(
        False, "--realtime", "-r", help="Run realtime report instead of date range"
    ),
) -> None:
    """Query Google Analytics 4 traffic and UTM campaign attribution."""
    try:
        from gtm_telemetry_wizard.cli import query_cmd

        query_cmd(property_id=property_id, campaign=campaign, path=path, days=days, realtime=realtime)
    except ImportError:
        typer.echo("Error: gtm_telemetry_wizard package is not installed.", err=True)
        raise typer.Exit(code=1)


@app.command(name="pull")
def pull_telemetry(
    property_id: Optional[str] = typer.Option(
        None, "--property-id", "-p", help="Google Analytics 4 Property ID (e.g. 555090946)"
    ),
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name override"
    ),
    initiative: Optional[str] = typer.Option(
        None, "--initiative", "-i", help="Specific initiative to filter (e.g. testimonials, rta)"
    ),
    days: int = typer.Option(
        7, "--days", "-d", help="Days of history to query"
    ),
) -> None:
    """Poll GA4 Data API for recent campaign hits with company/person attribution and append to local engagement log."""
    camp = campaign or get_campaign() or "roadmap"
    service = EngagementService(camp)
    typer.echo(f"Pulling GA4 telemetry for campaign '{camp}' (past {days} days)...")
    new_events = service.pull_from_ga4(property_id=property_id, initiative=initiative, days=days)
    if not new_events:
        typer.echo("No new prospect engagement signals found in GA4.")
        return

    typer.echo(f"Successfully pulled {len(new_events)} new engagement signal(s):")
    for evt in new_events:
        person_info = f" ({evt.utm_term})" if evt.utm_term else ""
        typer.echo(f"  - [{evt.event_type}] {evt.company_slug}{person_info} -> {evt.details.get('page_path')}")


@app.command(name="pull-clicks")
def pull_clicks_telemetry(
    property_id: Optional[str] = typer.Option(
        None, "--property-id", "-p", help="GA4 numeric property ID (defaults to campaign config)"
    ),
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name override"
    ),
    initiative: Optional[str] = typer.Option(
        None, "--initiative", "-i", help="Specific initiative to filter (e.g. testimonials, rta)"
    ),
    days: int = typer.Option(7, "--days", "-d", help="Days of history to query"),
) -> None:
    """Pull event-level GA4 data for cta_click: which specific button
    was clicked, on which page - the granularity `pull` (session-level)
    can't see. Requires button_label to already be registered as an
    event-scoped custom dimension (see `register-dimension`); clicks
    recorded before that registration are not retroactively queryable."""
    camp = campaign or get_campaign() or "roadmap"
    service = EngagementService(camp)
    typer.echo(f"Pulling GA4 cta_click event data for campaign '{camp}' (past {days} days)...")
    try:
        new_events = service.pull_cta_clicks(property_id=property_id, initiative=initiative, days=days)
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if not new_events:
        typer.echo("No new cta_click events found in GA4.")
        return

    typer.echo(f"Successfully pulled {len(new_events)} new cta_click event(s):")
    for evt in new_events:
        person_info = f" ({evt.utm_term})" if evt.utm_term else ""
        button = evt.details.get("button_label") or "(unlabeled)"
        typer.echo(f"  - {evt.company_slug or '(unmatched)'}{person_info} clicked '{button}' on {evt.details.get('page_path')}")


@app.command(name="register-dimension")
def register_dimension_telemetry(
    parameter_name: str = typer.Argument(..., help="Event parameter name as sent by the GTM tag (e.g. button_label)"),
    display_name: str = typer.Option(..., "--display-name", help="Human-readable name shown in the GA4 UI"),
    property_id: Optional[str] = typer.Option(
        None, "--property-id", "-p", help="GA4 numeric property ID (defaults to campaign config)"
    ),
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name override"
    ),
    description: str = typer.Option("", "--description", help="Optional description"),
) -> None:
    """Register an event-scoped GA4 custom dimension - a one-time,
    idempotent step required before an event parameter sent by a GTM tag
    becomes queryable via the Data API at all. Does not backfill past
    events; only events recorded after registration are affected."""
    from cocli.application.telemetry_service import GoogleTelemetryProvider
    from cocli.core.config import load_campaign_config

    camp = campaign or get_campaign() or "roadmap"
    campaign_cfg = load_campaign_config(camp)
    ga_cfg = campaign_cfg.get("google_analytics", {}) or {}
    p_id = property_id or ga_cfg.get("ga4_property_id")
    if not p_id:
        typer.echo(
            "Error: no GA4 property ID. Pass --property-id or set "
            "google_analytics.ga4_property_id in this campaign's config.toml.",
            err=True,
        )
        raise typer.Exit(code=1)

    provider = GoogleTelemetryProvider(camp)
    try:
        result = provider.register_event_custom_dimension(
            str(p_id), parameter_name, display_name, description
        )
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Registered: {result.get('name')}")
    typer.echo(f"  parameterName: {result.get('parameterName')}")
    typer.echo(f"  scope: {result.get('scope')}")


@app.command(name="process-testimonials")
def process_testimonials(
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name override"
    ),
    initiative: Optional[str] = typer.Option(
        "testimonials", "--initiative", "-i", help="Initiative to fall back to for first-name matching"
    ),
) -> None:
    """Process pending testimonial-form submissions - reads directly from
    S3, no prior sync step needed - into the engagement log and a
    company note, then mark each completed."""
    camp = campaign or get_campaign() or "roadmap"
    service = EngagementService(camp)
    new_events = service.process_testimonial_submissions(initiative=initiative)
    if not new_events:
        typer.echo("No pending testimonial submissions to process.")
        return

    typer.echo(f"Processed {len(new_events)} testimonial submission(s):")
    for evt in new_events:
        name = evt.details.get("name") or evt.details.get("email") or "(unknown)"
        match_status = evt.company_slug or "UNMATCHED"
        typer.echo(f"  - {name} -> {match_status}")


@app.command(name="report")
def report_telemetry(
    days: int = typer.Option(
        7, "--days", "-d", help="Only show submissions received in the last N days"
    ),
    today: bool = typer.Option(
        False, "--today", help="Shorthand for --days 1"
    ),
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name override"
    ),
) -> None:
    """Show form submissions (testimonials + signups) received in a time
    window, straight from S3 - both already-processed (completed/) and
    not-yet-processed (pending/) - so this always reflects reality even
    if `process-testimonials` hasn't been run yet."""
    from datetime import datetime
    from rich.console import Console
    from rich.table import Table

    camp = campaign or get_campaign() or "roadmap"
    window_days = 1 if today else days
    service = EngagementService(camp)
    submissions = service.list_form_submissions(since_days=window_days)

    console = Console()
    if not submissions:
        console.print(
            f"[yellow]No form submissions (testimonials or signups) in the last "
            f"{window_days} day(s).[/yellow]"
        )
        return

    table = Table(show_header=True)
    table.add_column("When", style="dim")
    table.add_column("Form")
    table.add_column("Status")
    table.add_column("Name")
    table.add_column("Email")
    table.add_column("UTM Source")

    for item in submissions:
        received_at = item.get("received_at")
        # received_at is a UTC unix timestamp; fromtimestamp() with no tz=
        # converts it to this machine's local timezone, which is what the
        # cocli operator actually wants to read, not the storage timezone.
        when = (
            datetime.fromtimestamp(received_at).astimezone().strftime("%Y-%m-%d %H:%M %Z")
            if received_at
            else "(unknown)"
        )
        table.add_row(
            when,
            str(item.get("_queue", "?")),
            str(item.get("_status", "?")),
            str(item.get("name") or ""),
            str(item.get("email") or ""),
            str(item.get("utm_source") or ""),
        )

    console.print(table)
    console.print(f"\n[bold]{len(submissions)}[/bold] submission(s) in the last {window_days} day(s).")


@app.command(name="pages")
def pages_telemetry(
    days: int = typer.Option(7, "--days", "-d", help="Number of past days to report on"),
    property_id: Optional[str] = typer.Option(
        None, "--property-id", "-p", help="GA4 numeric property ID (defaults to campaign config)"
    ),
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name override"
    ),
    limit: int = typer.Option(50, "--limit", "-l", help="Maximum number of pages to show"),
) -> None:
    """Per-page engagement breakdown for the landing page site: sessions,
    engagement rate, average time on page, pageviews, and event count -
    one row per page path, via the GA4 Data API. No new tracking needed;
    GA4 Enhanced Measurement already captures the underlying scroll/
    outbound-click/form-interaction signals these metrics are built from."""
    from rich.console import Console
    from rich.table import Table

    from cocli.application.telemetry_service import GoogleTelemetryProvider
    from cocli.core.config import load_campaign_config

    camp = campaign or get_campaign() or "roadmap"
    campaign_cfg = load_campaign_config(camp)
    ga_cfg = campaign_cfg.get("google_analytics", {}) or {}
    p_id = property_id or ga_cfg.get("ga4_property_id")
    if not p_id:
        typer.echo(
            "Error: no GA4 property ID. Pass --property-id or set "
            "google_analytics.ga4_property_id in this campaign's config.toml.",
            err=True,
        )
        raise typer.Exit(code=1)

    provider = GoogleTelemetryProvider(camp)
    try:
        rows = provider.query_page_engagement(str(p_id), days=days, limit=limit)
    except Exception as exc:
        typer.echo(f"Error querying GA4 Data API: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    console = Console()
    if not rows:
        console.print(f"[yellow]No page traffic recorded in the last {days} day(s).[/yellow]")
        return

    table = Table(show_header=True)
    table.add_column("Page Path")
    table.add_column("Sessions", justify="right")
    table.add_column("Engagement Rate", justify="right")
    table.add_column("Avg. Session Duration", justify="right")
    table.add_column("Pageviews", justify="right")
    table.add_column("Events", justify="right")

    for row in rows:
        engagement_rate = float(row.get("engagementRate", "0") or 0)
        avg_duration = float(row.get("averageSessionDuration", "0") or 0)
        table.add_row(
            row.get("pagePath", ""),
            row.get("sessions", "0"),
            f"{engagement_rate * 100:.1f}%",
            f"{avg_duration:.0f}s",
            row.get("screenPageViews", "0"),
            row.get("eventCount", "0"),
        )

    console.print(table)
    console.print(f"\n[bold]{len(rows)}[/bold] page(s) with traffic in the last {days} day(s).")

