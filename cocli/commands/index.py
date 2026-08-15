"""CLI adapter for index lifecycle commands (compact, status, backfill, datapackage)."""

from __future__ import annotations

import logging
from pathlib import Path
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


@app.command(name="sync-pi-wal")
def sync_pi_wal(
    campaign: str = typer.Option("roadmap", help="Campaign name"),
    index: str = typer.Option("google_maps_prospects", help="Index name whose WAL to sync"),
) -> None:
    """
    Pushes each Pi node's local index WAL to S3 (rsync Pi -> local staging,
    then upload staging -> S3), so `cocli index compact` has fresh data to
    fold. Scrapers write WAL entries directly to the Pi's local disk; nothing
    else moves that data to S3 automatically. Run this before `compact`, or
    let `cocli web deploy` run both in order.
    """
    from cocli.application.pi_sync_service import PiSyncService
    from rich.table import Table

    console.print(f"[bold]Syncing {index} WAL to S3 for {campaign}...[/bold]")
    service = PiSyncService(campaign)
    results = service.sync_prospect_wal_to_s3(index_name=index)

    if not results:
        console.print("[yellow]No Pi nodes configured for this campaign.[/yellow]")
        return

    table = Table(title="WAL Sync Results")
    table.add_column("Node")
    table.add_column("Status")
    table.add_column("Files Pushed", justify="right")
    for r in results:
        status = "[green]OK[/green]" if r.success else f"[red]FAILED: {r.error}[/red]"
        table.add_row(r.host, status, str(r.files_synced))
    console.print(table)

    if not all(r.success for r in results):
        raise typer.Exit(code=1)


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


@app.command(name="trace")
def trace(
    place_id: Optional[str] = typer.Argument(
        None, help="Single place_id to trace end to end."
    ),
    from_file: Optional[Path] = typer.Option(
        None, "--from-file", help="File of place_ids, one per line, for batch mode."
    ),
    campaign: str = typer.Option("roadmap", help="Campaign name"),
    index: str = typer.Option("google_maps_prospects", help="Index name"),
    out: Optional[Path] = typer.Option(
        None, "--out",
        help="Write batch results to this CSV path. Defaults to a "
        "timestamped file under the campaign's own exports/ directory "
        "(campaigns/{campaign}/exports/) - pass an explicit path only to "
        "override that.",
    ),
) -> None:
    """
    Trace one or more place_ids across every station of the pipeline
    (gm-list -> gm-details -> Pi WAL -> checkpoint) to find exactly where a
    record's trail goes cold. Pass a single place_id for a one-off audit, or
    --from-file for a batch group report (one row per place_id), written to
    the campaign's exports/ directory by default - this is campaign data,
    it doesn't belong at the repo root or wherever the shell happened to be.
    """
    if not place_id and not from_file:
        console.print("[red]Provide a place_id argument or --from-file.[/red]")
        raise typer.Exit(1)
    if place_id and from_file:
        console.print("[red]Provide either a place_id or --from-file, not both.[/red]")
        raise typer.Exit(1)

    if place_id:
        ids = [place_id]
    else:
        assert from_file is not None
        ids = [line.strip() for line in from_file.read_text().splitlines() if line.strip()]

    services = ServiceContainer(campaign_name=campaign)
    result = services.index_service.trace_prospects(ids, index_name=index)

    if not result.rows:
        console.print("[yellow]No place_ids to trace.[/yellow]")
        return

    if len(result.rows) == 1:
        row = result.rows[0]
        console.print(f"place_id: [bold]{row.place_id}[/bold]")
        console.print(f"  gm-list:    {row.gm_list}")
        console.print(f"  gm-details: {row.gm_details}")
        console.print(f"  pi-wal:     {row.pi_wal}")
        console.print(f"  checkpoint: {row.checkpoint}")
        console.print(f"  [bold]verdict:[/bold] {row.verdict}")
        return

    from rich.table import Table

    table = Table(title=f"Prospect trace: {len(result.rows)} place_ids")
    table.add_column("place_id")
    table.add_column("gm-list")
    table.add_column("gm-details")
    table.add_column("pi-wal")
    table.add_column("checkpoint")
    table.add_column("verdict")
    for row in result.rows:
        table.add_row(
            row.place_id, row.gm_list, row.gm_details, row.pi_wal,
            row.checkpoint, row.verdict,
        )
    console.print(table)

    import csv

    if out is None:
        from datetime import datetime

        from cocli.core.config import get_campaign_exports_dir

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = get_campaign_exports_dir(campaign) / f"prospect_trace_{index}_{timestamp}.csv"
    else:
        out.parent.mkdir(parents=True, exist_ok=True)

    with open(out, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["place_id", "gm_list", "gm_details", "pi_wal", "checkpoint", "verdict"]
        )
        for row in result.rows:
            writer.writerow(
                [row.place_id, row.gm_list, row.gm_details, row.pi_wal,
                 row.checkpoint, row.verdict]
            )
    console.print(f"\n[green]Wrote {len(result.rows)} rows to {out}[/green]")

    from collections import Counter

    tally = Counter(
        r.verdict.split(" - ")[0] if " - " in r.verdict else r.verdict
        for r in result.rows
    )
    console.print("\n[bold]Verdict summary:[/bold]")
    for verdict, count in tally.most_common():
        console.print(f"  {count:4d}  {verdict}")


@app.command(name="requeue-stuck-details")
def requeue_stuck_details(
    place_id: Optional[str] = typer.Argument(
        None, help="Single place_id to requeue."
    ),
    from_file: Optional[Path] = typer.Option(
        None, "--from-file", help="File of place_ids, one per line, for batch mode."
    ),
    campaign: str = typer.Option("roadmap", help="Campaign name"),
    index: str = typer.Option("google_maps_prospects", help="Index name"),
) -> None:
    """
    Recover gm-details tasks that were acked with no real output - the
    gm-details-acks-unconditionally incident, fixed in worker_service.py.
    Rebuilds the task from its own stale completed/{place_id}.json marker
    (already synced locally) and pushes it directly onto one Pi node's
    gm-details queue over SSH (pending/ never syncs Pi<->dev-machine, so
    this can't be done locally), after removing the stale marker everywhere.

    Use `cocli index trace` first to confirm a place_id is actually stuck
    (gm-details: completed, pi-wal/checkpoint: absent) before requeuing it.
    """
    if not place_id and not from_file:
        console.print("[red]Provide a place_id argument or --from-file.[/red]")
        raise typer.Exit(1)
    if place_id and from_file:
        console.print("[red]Provide either a place_id or --from-file, not both.[/red]")
        raise typer.Exit(1)

    if place_id:
        ids = [place_id]
    else:
        assert from_file is not None
        ids = [line.strip() for line in from_file.read_text().splitlines() if line.strip()]

    services = ServiceContainer(campaign_name=campaign)
    result = services.index_service.requeue_stuck_details(ids, index_name=index)

    from rich.table import Table

    table = Table(title=f"Requeue stuck details: {len(result.rows)} place_ids")
    table.add_column("place_id")
    table.add_column("status")
    table.add_column("detail")
    for row in result.rows:
        color = {"requeued": "green", "not_found": "yellow", "ssh_error": "red"}.get(row.status, "white")
        table.add_row(row.place_id, f"[{color}]{row.status}[/{color}]", row.detail)
    console.print(table)

    if any(r.status != "requeued" for r in result.rows):
        raise typer.Exit(code=1)


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
