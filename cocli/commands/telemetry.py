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
    skip_verify: bool = typer.Option(False, "--skip-verify", help="Skip Playwright live URL verification"),
) -> None:
    """Guided wizard for inspecting status, syncing IaC spec, verifying live site, and deploying GTM across Google accounts."""
    _, _, wizard_cmd, _ = _get_wizard_cmds()
    wizard_cmd(domain=domain, container_id=container_id, ga4_id=None, config=None, skip_verify=skip_verify)
