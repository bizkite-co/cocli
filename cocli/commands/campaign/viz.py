"""CLI adapter for campaign visualization / KML publish commands."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from typing_extensions import Annotated

from cocli.application.services import ServiceContainer
from cocli.core.config import get_campaign

logger = logging.getLogger(__name__)
console = Console()
app = typer.Typer(no_args_is_help=True)


def _resolve_campaign(campaign_name: Optional[str]) -> str:
    name = campaign_name or get_campaign()
    if not name:
        console.print(
            "[red]Error: No campaign name provided and no campaign context is set.[/red]"
        )
        raise typer.Exit(code=1)
    return name


@app.command(name="visualize-coverage")
def visualize_coverage(
    campaign_name: Optional[str] = typer.Argument(
        None,
        help="Name of the campaign to visualize. If not provided, uses the current campaign context.",
    ),
) -> None:
    """
    Generates KML/GeoJSON for the campaign map-tile grid (item counts + scrape status).
    """
    name = _resolve_campaign(campaign_name)
    services = ServiceContainer(campaign_name=name)
    try:
        result = services.reporting_service.generate_coverage_kml(campaign_name=name)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)

    if result.count == 0:
        console.print(f"[yellow]{result.message}[/yellow]")
        return

    console.print(f"[bold green]{result.message}[/bold green]")


@app.command(name="visualize-legacy-scrapes")
def visualize_legacy_scrapes(
    campaign_name: Optional[str] = typer.Argument(
        None,
        help="Name of the campaign. If not provided, uses the current campaign context.",
    ),
) -> None:
    """
    Generates a KML file for all legacy (non-grid-aligned) scraped areas.
    """
    name = campaign_name or get_campaign()
    if not name:
        return

    services = ServiceContainer(campaign_name=name)
    try:
        result = services.reporting_service.generate_legacy_scrapes_kml(
            campaign_name=name
        )
    except ValueError:
        return

    if result.count == 0:
        console.print(f"[yellow]{result.message}[/yellow]")
        return

    console.print(f"[bold green]{result.message}[/bold green]")


@app.command(name="mark-wilderness")
def mark_wilderness(
    tile_id: str = typer.Argument(..., help="Southwest-corner tile id, e.g. 33.5_-116.0"),
    unmark: bool = typer.Option(
        False, "--unmark", help="Remove the wilderness mark instead of adding it."
    ),
) -> None:
    """Mark (or unmark) a global wilderness tile used by every campaign's scrapes."""
    from cocli.core.scrape_index import ScrapeIndex

    index = ScrapeIndex()
    if unmark:
        if index.unmark_wilderness_tile(tile_id):
            console.print(f"[green]Unmarked wilderness tile {tile_id}[/green]")
        else:
            console.print(f"[yellow]Tile {tile_id} was not marked wilderness.[/yellow]")
        return
    path = index.mark_wilderness_tile(tile_id, marked_by="cli")
    if path is None:
        console.print(f"[red]Invalid tile id: {tile_id}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Marked wilderness tile {tile_id}[/green]")


@app.command("publish-kml")
def publish_kml(
    campaign_name: Annotated[
        Optional[str],
        typer.Argument(
            help="Name of the campaign. If not provided, uses the current campaign context."
        ),
    ] = None,
    bucket_name: Optional[str] = typer.Option(None, "--bucket", help="S3 bucket name."),
    domain: Optional[str] = typer.Option(
        None,
        "--domain",
        help="Public domain name for KML URLs (required by Google Maps).",
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="AWS profile to use."
    ),
    skip_generate: bool = typer.Option(
        False,
        "--skip-generate",
        help="Upload already-generated exports only (skip grid/coverage/prospects rebuild).",
    ),
) -> None:
    """
    Generates all KMLs (Customers, Prospects, Coverage) and uploads them to S3.
    """
    name = _resolve_campaign(campaign_name)
    logging.getLogger("cocli").setLevel(logging.WARNING)
    services = ServiceContainer(campaign_name=name)

    def log_cb(msg: str) -> None:
        if msg.startswith("✓") or msg.startswith("Published"):
            console.print(f"[green]{msg}[/green]")
        elif msg.startswith("Error"):
            console.print(f"[bold red]{msg}[/bold red]")
        else:
            console.print(f"[dim]{msg}[/dim]")

    try:
        result = services.reporting_service.publish_kml(
            profile=profile,
            bucket_name=bucket_name,
            domain=domain,
            campaign_name=name,
            log_callback=log_cb,
            generate=not skip_generate,
        )
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)

    if not result.success:
        console.print(f"[bold red]{result.message}[/bold red]")
        raise typer.Exit(code=1)


@app.command("upload-kml-coverage")
def upload_kml_coverage_for_turboship(
    campaign_name: str = typer.Argument("turboship", help="Name of the campaign."),
    turboship_kml_exports_path: Path = typer.Option(
        "../turboheatweldingtools/turboship/data/kml-exports",
        "--turboship-kml-exports-path",
    ),
    kml_filename: str = typer.Option("turboship_coverage.kml", "--filename"),
    kml_type: str = typer.Option("customers", "--type"),
) -> None:
    """
    Legacy command for manual placement into turboship repo.
    """
    if not campaign_name:
        raise typer.Exit(code=1)

    services = ServiceContainer(campaign_name=campaign_name)
    try:
        result = services.reporting_service.place_kml_for_turboship(
            campaign_name=campaign_name,
            turboship_kml_exports_path=turboship_kml_exports_path,
            kml_filename=kml_filename,
            kml_type=kml_type,
        )
    except ValueError:
        raise typer.Exit(code=1)

    if not result.success:
        raise typer.Exit(code=1)

    console.print(f"[green]{result.message}[/green]")


@app.command(name="export-resources")
def export_resources(
    campaign_name: Optional[str] = typer.Argument(None),
) -> None:
    """
    Aggregates and exports "Value-First" resources from the campaign index.
    Optimized for Astro site ingestion.
    """
    name = _resolve_campaign(campaign_name)
    services = ServiceContainer(campaign_name=name)
    try:
        result = services.reporting_service.export_value_resources(campaign_name=name)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    if result.count == 0 and "No index found" in result.message:
        console.print(f"[yellow]{result.message}[/yellow]")
        return

    console.print(f"[bold green]{result.message}[/bold green]")
