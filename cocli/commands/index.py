"""CLI adapter for index lifecycle commands (compact, status, backfill, datapackage)."""

from __future__ import annotations

import logging
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from cocli.application.index_service import (
    SchemaConflictError,
    setup_index_log_file,
)
from cocli.application.services import ServiceContainer

console = Console()
logger = logging.getLogger(__name__)

app = typer.Typer(help="Commands for managing sharded indexes.", no_args_is_help=True)


def _configure_compact_logging(log_file_path: object, debug: bool) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(str(log_file_path))],
        force=True,
    )
    for name in ["botocore", "boto3", "urllib3", "duckdb"]:
        logging.getLogger(name).setLevel(logging.WARNING)
    if debug:
        logging.getLogger("cocli").setLevel(logging.DEBUG)


@app.command(name="compact")
def compact(
    campaign: str = typer.Option("roadmap", help="Campaign name"),
    index: str = typer.Option("google_maps_prospects", help="Index name to compact"),
    debug: bool = typer.Option(False, help="Enable debug logging"),
) -> None:
    """
    Compact the Write-Ahead Log (WAL) into the main Checkpoint.
    Uses S3-Native isolation to prevent race conditions.
    """
    log_file = setup_index_log_file(campaign, index)
    _configure_compact_logging(log_file, debug)

    console.print(f"Compacting index [bold]{index}[/bold] for [bold]{campaign}[/bold]")
    console.print(f"Detailed logs: [cyan]{log_file}[/cyan]")

    services = ServiceContainer(campaign_name=campaign)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task_id = progress.add_task("Starting compaction...", total=None)

        def log_cb(msg: str) -> None:
            # Live step updates during long S3-bound FIMC work (cluster idiom).
            progress.update(task_id, description=msg)

        result = services.index_service.compact(
            index_name=index,
            log_file=log_file,
            log_callback=log_cb,
        )

    if not result.success:
        console.print(f"[bold red]{result.message}[/bold red]")
        raise typer.Exit(code=1)

    if result.isolated_files == 0 and result.message == "Nothing to compact.":
        console.print("[yellow]Nothing to compact.[/yellow]")
        return

    console.print(f"[bold green]{result.message}[/bold green]")


@app.command(name="status")
def status(
    campaign: str = typer.Option("roadmap", help="Campaign name"),
    index: str = typer.Option("google_maps_prospects", help="Index name"),
) -> None:
    """
    Show the status of the index tiers (WAL, Processing, Checkpoint).
    """
    services = ServiceContainer(campaign_name=campaign)
    report = services.index_service.get_status(index_name=index)

    console.print(
        f"Status for index [bold]{report.index_name}[/bold] "
        f"in campaign [bold]{report.campaign_name}[/bold]:"
    )

    if report.lock.error:
        console.print(f"Lock: [red]Error checking lock: {report.lock.error}[/red]")
    elif report.lock.active:
        console.print(
            f"[bold yellow]LOCK ACTIVE[/bold yellow]: Run ID {report.lock.run_id} "
            f"started at {report.lock.created_at} on {report.lock.host}"
        )
    else:
        console.print("Lock: [green]Available[/green]")

    console.print(
        f"WAL Backlog (Hot): [bold cyan]{report.wal_backlog_count}[/bold cyan] "
        "files waiting for checkpointing."
    )

    if report.processing_file_count > 0:
        console.print(
            f"Processing (Staging): [bold yellow]{report.processing_file_count}[/bold yellow] "
            "files currently isolated."
        )
    else:
        console.print("Processing: [green]Empty[/green]")

    cp = report.checkpoint
    if cp.error:
        console.print(f"Checkpoint: [red]Error: {cp.error}[/red]")
    elif cp.found:
        console.print(
            f"Checkpoint (Cold): [bold blue]{cp.size_mb:.2f} MB[/bold blue] "
            f"(Last updated: {cp.last_modified})"
        )
    else:
        console.print("Checkpoint: [red]Not found[/red]")


@app.command(name="backfill-domains")
def backfill_domains(
    campaign: str = typer.Option("roadmap", help="Campaign name"),
    limit: int = typer.Option(
        0, "--limit", "-l", help="Limit the number of companies processed (for testing)."
    ),
    compact: bool = typer.Option(
        True,
        "--compact/--no-compact",
        help="Automatically run compaction after backfill.",
    ),
) -> None:
    """
    Backfill the Domain Index from local website enrichment files.
    """
    console.print(f"Backfilling Domain Index for campaign: [bold]{campaign}[/bold]")

    services = ServiceContainer(campaign_name=campaign)
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task_id = progress.add_task("Starting domain backfill...", total=None)

            def log_cb(msg: str) -> None:
                progress.update(task_id, description=msg)

            result = services.index_service.backfill_domains(
                limit=limit,
                compact=compact,
                log_callback=log_cb,
            )
    except Exception as e:
        console.print(f"[bold red]Error loading campaign:[/bold red] {e}")
        raise typer.Exit(1)

    console.print(
        f"[bold green]Success![/bold green] Backfill process finished for "
        f"[cyan]{campaign}[/cyan] "
        f"({result.records_added} records, tag '{result.tag}')."
    )


@app.command(name="write-datapackage", no_args_is_help=True)
def write_datapackage(
    index: str = typer.Argument(
        ..., help="Index name (e.g. domains, google_maps_prospects)"
    ),
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name for campaign-specific indexes."
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force overwrite even if schema change is breaking."
    ),
) -> None:
    """
    Generates Frictionless Data 'datapackage.json' for the specified index based on its Pydantic model.
    """
    services = ServiceContainer(campaign_name=campaign or "")
    try:
        result = services.index_service.write_datapackage(
            index_name=index, force=force, campaign=campaign
        )
        console.print(f"[green]{result.message}[/green]")
    except ValueError as e:
        # ValueError (not KeyError): str(KeyError) wraps the message in repr quotes.
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except SchemaConflictError as e:
        console.print("[bold red]SCHEMA CONFLICT ERROR[/bold red]")
        console.print(f"[red]{e}[/red]")
        console.print("[yellow]Detected Positional Drift:[/yellow]")
        for line in e.diff:
            console.print(f"  [red]{line}[/red]")
        console.print(
            "\n[bold]Prevention:[/bold] USV is positional. "
            "Only add new fields to the END of the model."
        )
        console.print(
            "[dim]Use --force if you are performing a planned migration.[/dim]"
        )
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Failed to write datapackage: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
