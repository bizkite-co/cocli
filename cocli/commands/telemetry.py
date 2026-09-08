from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

import typer

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
