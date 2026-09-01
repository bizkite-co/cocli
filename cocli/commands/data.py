"""CLI adapter for frictionless data inspection and queue data ops."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from cocli.application.data_sync_service import (
    DataSyncService,
    UnknownColumnError,
)
from cocli.application.services import ServiceContainer

logger = logging.getLogger(__name__)

app = typer.Typer(no_args_is_help=True)
console = Console()

queue_app = typer.Typer(help="Queue management commands", no_args_is_help=True)
app.add_typer(queue_app, name="queue")

job_run_app = typer.Typer(help="Scrape job run inspection commands", no_args_is_help=True)
app.add_typer(job_run_app, name="job-run")


def _service() -> DataSyncService:
    return ServiceContainer().data_sync_service  # type: ignore[return-value]


@app.command(name="list")
def list_schemas() -> None:
    """List all known frictionless data schemas (datapackage.json files) in the project."""
    packs = _service().list_datapackages()
    table = Table(title="Frictionless Datapackages")
    table.add_column("Path", style="cyan")
    table.add_column("Resources")
    for dp in packs:
        table.add_row(dp.relative_path, ", ".join(dp.resource_names))
    console.print(table)


@app.command(no_args_is_help=True)
def describe(file_path: Path) -> None:
    """Show the schema definition (fields/types) for a given USV file or datapackage."""
    try:
        result = _service().describe_schema(file_path)
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    # If input was datapackage/dir, print each resource; if USV, one schema with "from {dp}".
    input_is_pkg = file_path.name == "datapackage.json" or (
        file_path.is_dir() and (file_path / "datapackage.json").exists()
    )
    if input_is_pkg:
        for res in result.resources:
            console.print(f"[bold]Schema for {res['name']}[/bold]")
            console.print(f"[dim]path: {res.get('path')}[/dim]")
            for field in res["fields"]:
                console.print(
                    f"{field['index']}: {field['name']} ({field.get('type', 'string')})"
                )
            console.print()
        return

    res = result.resources[0]
    console.print(f"[bold]Schema for {result.source_label}[/bold]")
    if result.datapackage_path:
        console.print(f"[dim]from {result.datapackage_path}[/dim]")
    for field in res["fields"]:
        console.print(
            f"{field['index']}: {field['name']} ({field.get('type', 'string')})"
        )


@app.command(no_args_is_help=True)
def locate(file_path: Path) -> None:
    """Find and display the datapackage.json for a given file."""
    dp = _service().locate_datapackage(file_path)
    if dp:
        console.print(f"[green]Found: {dp}[/green]")
    else:
        console.print("[red]No datapackage.json found[/red]")


@app.command(no_args_is_help=True)
def sample(
    file_path: Path,
    limit: int = typer.Option(10, "--limit", "-n"),
    text_only: bool = typer.Option(
        False, "--text", help="Output as plain text for narrow terminals."
    ),
    resource_name: Optional[str] = typer.Option(
        None,
        "--resource",
        help="Resource name to use if file_path is a datapackage/directory.",
    ),
) -> None:
    """Show first N rows with column names from a USV file."""
    try:
        result = _service().sample_rows(
            file_path, limit=limit, resource_name=resource_name
        )
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if text_only:
        for row in result.rows:
            for col, val in zip(result.columns, row):
                console.print(f"{col}: {val}")
            console.print("-" * 20)
        return

    table = Table(title=result.title)
    for col in result.columns:
        table.add_column(col)
    for row in result.rows:
        table.add_row(*[str(val) for val in row])
    console.print(table)


@app.command(name="retrofit-personnel-names", no_args_is_help=True)
def retrofit_personnel_names(
    campaign: str = typer.Option(..., "--campaign", "-c", help="Campaign name"),
    apply: bool = typer.Option(False, "--apply", help="Actually write updates (default is dry-run)."),
) -> None:
    """Backfill person: tags onto already-indexed emails whose name wasn't
    recoverable before the FIRST_NAMES dictionary gate was relaxed.

    Needs no re-scraping: a firstname.lastname@domain shape is already
    fully present in the email address itself. Uses the exact same
    inference function the live scraper uses
    (WebsiteScraper.infer_name_from_dotted_mailbox), so this can never
    silently drift from production behavior.

    Writes to the hot inbox - run `cocli data compact-emails` afterward to
    fold results into shards.

    Example: cocli data retrofit-personnel-names --campaign roadmap --apply
    """
    from cocli.application.email_personnel_retrofit import retrofit_personnel_names as _retrofit

    dry_run = not apply
    console.print(
        f"[cyan]{'[DRY RUN] ' if dry_run else ''}Retrofitting personnel names for campaign '{campaign}'...[/cyan]"
    )
    result = _retrofit(campaign, dry_run=dry_run)
    console.print(f"Scanned: {result.scanned}  Matched: {result.matched}")
    if result.sample_names:
        console.print(f"Sample names: {', '.join(result.sample_names)}")
    if dry_run:
        console.print("[yellow]Dry run - no changes written. Re-run with --apply to write.[/yellow]")
    else:
        console.print("[green]Done.[/green]")


@app.command(name="compact-emails", no_args_is_help=True)
def compact_emails(
    campaign: str = typer.Option(..., "--campaign", "-c", help="Campaign name"),
) -> None:
    """Compact the email index's hot inbox into cold shards (Hot Inbox -> Shards).

    EmailIndexManager.compact() already existed but was only reachable from
    the TUI's "Compact Email Index" menu item - no CLI path, which is why
    real inbox data can pile up uncompacted on a Pi node indefinitely with
    nobody noticing (confirmed live 2026-08-20: roadmap had 46,971 real
    inbox files and an empty shards/ dir).

    Example: cocli data compact-emails --campaign roadmap
    """
    console.print(f"[cyan]Compacting email index for campaign '{campaign}'...[/cyan]")
    result = ServiceContainer(campaign_name=campaign).data_sync_service.compact_index()
    if result.get("status") != "success":
        console.print(f"[red]{result.get('message')}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]{result.get('message')}[/green]")


@app.command(name="export-enriched-emails", no_args_is_help=True)
def export_enriched_emails_cmd(
    campaign: str = typer.Option(..., "--campaign", "-c", help="Campaign name"),
    keywords: bool = typer.Option(False, "--keywords", help="Only export companies that have found keywords (enriched)."),
    include_all: bool = typer.Option(False, "--all", "-a", help="Include all prospects even if they have no emails."),
) -> None:
    """Joins the prospects checkpoint against the email index and writes the
    client-facing enriched-emails USV + CSV (the export the dashboard's
    "download CSV" button and `cocli web deploy` both consume).

    This is the single, tested source of truth for that query - see
    cocli/application/lead_export_service.py's docstring and
    docs/data-management/data-quality-incidents/README.md for why that
    matters (a hand-rolled reimplementation of this query undercounted real
    results by ~18% during this session's investigation).

    Does not upload to S3 - that's `cocli web deploy`'s job. This command
    only writes the local .usv/.csv files, for inspection or a manual push.

    Example: cocli data export-enriched-emails --campaign turboship
    """
    from cocli.application.lead_export_service import export_enriched_emails

    console.print(f"[cyan]Exporting enriched emails for campaign '{campaign}'...[/cyan]")
    try:
        result = export_enriched_emails(campaign, keywords=keywords, include_all=include_all)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Exported: {result.exported_count} companies[/green]")
    if result.skipped_count:
        console.print(f"[yellow]Skipped: {result.skipped_count} records without phone/category/keyword signal[/yellow]")
    console.print(f"Output: {result.output_usv}")
    console.print(f"Output: {result.output_csv}")


@app.command(no_args_is_help=True)
def metrics(
    file_path: Path = typer.Argument(
        ..., help="Path to USV file or datapackage.json"
    ),
    resource_name: str = typer.Option(
        None,
        "--resource",
        help="Resource name to use if file_path is a datapackage.json.",
    ),
    output_path: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Write report to file (Markdown)."
    ),
) -> None:
    """Compute data quality metrics for a USV dataset (or datapackage)."""

    def log_cb(msg: str) -> None:
        console.print(f"[yellow]{msg}[/yellow]")

    try:
        result = _service().compute_metrics(
            file_path,
            resource_name=resource_name,
            output_path=output_path,
            log_callback=log_cb,
        )
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    title = (
        f"Metrics: {result.source_name} (fallback)"
        if result.used_fallback
        else f"Metrics: {result.source_name}"
    )

    table = Table(title=title)
    table.add_column("Metric")
    table.add_column("Count", justify="right")
    table.add_column("Percentage", justify="right")
    for metric, value in result.metrics.items():
        pct_str = f"{value.percentage:.1f}%" if value.percentage is not None else "-"
        table.add_row(metric, str(value.count), pct_str)
    console.print(table)

    if result.message:
        console.print(f"[green]{result.message}[/green]")


@app.command(no_args_is_help=True)
def search(
    file_path: Path,
    query: str = typer.Argument(
        ..., help="SQL-like WHERE clause to search the USV file."
    ),
    columns: str = typer.Option(
        "slug, phone, reviews_count", help="Comma-separated columns to select."
    ),
) -> None:
    """Provide a schema-aware search interface for USV files using DuckDB."""
    try:
        result = _service().search_usv(file_path, query=query, columns=columns)
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    except UnknownColumnError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print(f"[dim]Valid columns: {e.valid_preview}...[/dim]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error querying data: {e}[/red]")
        raise typer.Exit(1)

    if result.schema_warning:
        console.print(f"[yellow]Warning: {result.schema_warning}[/yellow]")

    table = Table(title=f"Search Results: {result.query}")
    for col in result.columns:
        table.add_column(col)
    for row in result.rows:
        table.add_row(*[str(val) if val is not None else "NULL" for val in row])
    console.print(table)
    console.print(f"[dim]{result.row_count} rows returned[/dim]")


@app.command(no_args_is_help=True)
def inspect(
    file_path: Path,
    row_number: int = typer.Option(
        1, "--row-number", "-r", help="Row number to inspect (1-indexed)."
    ),
) -> None:
    """Show the index, name, and content for a specific row in a USV file."""
    try:
        result = _service().inspect_row(file_path, row_number=row_number)
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    console.print(
        f"[bold]Inspection for {result.file_name}, Row {result.row_number}:[/bold]"
    )
    for i, name, val in result.fields:
        console.print(f"{i}: {name:<20} | {val}")


@queue_app.command(name="compact", no_args_is_help=True)
def queue_compact(
    campaign: str = typer.Option(
        "roadmap", "--campaign", "-c", help="Campaign name"
    ),
    queue_name: str = typer.Argument(
        ..., help="Queue name to compact (e.g., gm-list)"
    ),
) -> None:
    """Compact a queue's results into a unified dataset.

    Example: cocli data queue compact gm-list
    """
    console.print(
        f"[cyan]Compacting queue '{queue_name}' for campaign '{campaign}'...[/cyan]"
    )
    try:
        result = _service().compact_queue(queue_name, campaign_name=campaign)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]{result.message}[/green]")


@queue_app.command(name="reconcile", no_args_is_help=True)
def queue_reconcile(
    left: Path = typer.Argument(..., help="First directory of task/result files"),
    right: Path = typer.Argument(..., help="Second directory of task/result files"),
    strip_leading_segments: int = typer.Option(
        1,
        help="Path segments to drop before comparing identity (default 1, "
        "to ignore a leading shard-bucket directory)",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show a sample of mismatched identities"
    ),
    sample_limit: int = typer.Option(
        10, help="Max sample IDs to print per category with --verbose"
    ),
) -> None:
    """Diff two directory trees of task/result files by normalized identity.

    Generic reconciliation for any two queue-shaped directories - not
    specific to any one queue. Identity is the relative path with its
    extension stripped and the leading shard-bucket segment removed;
    bookkeeping files (lease/attempts sidecars, datapackage.json, etc.)
    are excluded automatically.

    Example: cocli data queue reconcile data/campaigns/roadmap/queues/discovery-gen/completed data/campaigns/roadmap/queues/gm-list/completed/results
    """
    from cocli.core.queue.reconcile import reconcile_identities

    result = reconcile_identities(left, right, strip_leading_segments=strip_leading_segments)

    table = Table(title=f"Reconciliation: {left.name} vs {right.name}")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")
    table.add_row(f"Left total ({left})", str(result.left_total))
    table.add_row(f"Right total ({right})", str(result.right_total))
    table.add_row("Matched", str(result.matched))
    left_style = "yellow" if result.left_only else "green"
    right_style = "yellow" if result.right_only else "green"
    table.add_row("Left-only", f"[{left_style}]{len(result.left_only)}[/{left_style}]")
    table.add_row("Right-only", f"[{right_style}]{len(result.right_only)}[/{right_style}]")
    console.print(table)

    if verbose:
        def _print_sample(title: str, ids: frozenset[str]) -> None:
            if not ids:
                return
            sorted_ids = sorted(ids)
            console.print(f"\n[bold]{title}[/bold] (showing up to {sample_limit} of {len(sorted_ids)}):")
            for i in sorted_ids[:sample_limit]:
                console.print(f"  • {i}")

        _print_sample("Left-only", result.left_only)
        _print_sample("Right-only", result.right_only)


@queue_app.command(name="enqueue-gm-list", no_args_is_help=True)
def queue_enqueue_gm_list(
    campaign: str = typer.Option(..., "--campaign", "-c", help="Campaign name"),
    limit: Optional[int] = typer.Option(
        None, help="Copy at most this many items (default: all unscraped items)"
    ),
    rescrape_all: bool = typer.Option(
        False,
        "--rescrape-all",
        help="Copy everything from discovery-gen/completed, including items "
        "with an existing gm-list completed receipt - for a deliberate full "
        "re-scrape. Default only copies items with no receipt yet.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview what would be copied without writing files"
    ),
) -> None:
    """Copy discovery-gen/completed/ -> gm-list/pending/.

    A real, transformation-free file copy - both sides are already
    ScrapeTask-shaped at the same relative path. Default behavior skips
    anything with an existing gm-list completed receipt; --rescrape-all
    bypasses that. Use --limit to enqueue a bounded batch at a time.
    """
    from cocli.application.gm_list_enqueue_service import enqueue_unscraped_to_gm_list_pending

    result = enqueue_unscraped_to_gm_list_pending(
        campaign_name=campaign, limit=limit, rescrape_all=rescrape_all, dry_run=dry_run
    )

    verb = "Would copy" if dry_run else "Copied"
    console.print(f"[cyan]Candidates: {result.candidates}[/cyan]")
    if not rescrape_all:
        console.print(f"[dim]Skipped (already scraped): {result.skipped_already_scraped}[/dim]")
    console.print(f"[green]{verb} {result.copied} item(s) into gm-list/pending/[/green]")


@job_run_app.command(name="list")
def job_run_list(
    campaign: str = typer.Option(..., "--campaign", "-c", help="Campaign name"),
    limit: int = typer.Option(20, help="Show at most this many runs, most recent first"),
) -> None:
    """List ScrapeJobRuns for a campaign - the explicit lineage between a
    discovery-gen batch and its scrape progress (see
    cocli/models/campaigns/scrape_job_run.py). A run with no
    discovery_gen_completed_at is still generating; no started_at means
    it's waiting on (or stuck on) its auto-copy into gm-list/pending/; no
    gm_list_completed_at means gm-list scraping is still in progress.
    """
    from cocli.application.job_run_service import _load_index

    runs = sorted(_load_index(campaign), key=lambda r: r.created_at, reverse=True)[:limit]

    table = Table(title=f"Job Runs: {campaign}")
    table.add_column("ID")
    table.add_column("Created")
    table.add_column("Discovery-Gen Done")
    table.add_column("Started")
    table.add_column("GM-List Done")
    table.add_column("Identities", justify="right")

    def _fmt(value: object) -> str:
        return str(value) if value else "[dim]-[/dim]"

    for run in runs:
        table.add_row(
            run.id,
            run.created_at.isoformat(timespec="seconds"),
            _fmt(run.discovery_gen_completed_at),
            _fmt(run.started_at),
            _fmt(run.gm_list_completed_at),
            str(run.identity_count),
        )

    console.print(table)


@job_run_app.command(name="requeue")
def job_run_requeue(
    run_id: Optional[str] = typer.Argument(None, help="Job run ID to re-scrape"),
    campaign: str = typer.Option(..., "--campaign", "-c", help="Campaign name"),
    latest: bool = typer.Option(
        False, "--latest", help="Re-scrape the most recently created run instead of naming one"
    ),
) -> None:
    """Create a new ScrapeJobRun that re-scrapes a run's exact identity
    set, bypassing the "already gm-list-completed" filter - every
    identity in a finished run trivially has a receipt, or it wouldn't be
    finished. For the "haven't scraped this campaign in N months, there
    might be new data" case: re-runs the same discovery-gen tiles/phrases
    without regenerating them. Pass either a run ID or --latest, not both.
    """
    from cocli.application.job_run_service import get_latest_job_run, requeue_job_run

    if latest == bool(run_id):
        console.print("[red]Pass exactly one of: a job run ID, or --latest.[/red]")
        raise typer.Exit(1)

    if latest:
        latest_run = get_latest_job_run(campaign)
        if latest_run is None:
            console.print(f"[red]No job runs found for campaign '{campaign}'.[/red]")
            raise typer.Exit(1)
        run_id = latest_run.id

    assert run_id is not None  # guaranteed by the exclusivity check above

    try:
        new_run = requeue_job_run(campaign, run_id)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    console.print(f"[bold green]Job run {new_run.id}[/bold green]")
    console.print(f"  Re-scraping {new_run.identity_count} identities from {run_id}")
    console.print("  Enqueued into gm-list/pending/ (rescrape_all)")
