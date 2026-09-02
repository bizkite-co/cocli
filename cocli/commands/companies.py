from __future__ import annotations
from typing import Optional

import typer
from rich.console import Console

from ..core.config import get_companies_dir

app = typer.Typer(no_args_is_help=True)
console = Console()

@app.command("list-recent")
def list_recent(
    count: int = typer.Option(10, "--count", "-c", help="The number of recent companies to list.")
) -> None:
    """
    Lists the most recently created companies.
    """
    companies_dir = get_companies_dir()
    if not companies_dir.exists():
        console.print("[bold red]Companies directory not found.[/bold red]")
        raise typer.Exit(code=1)

    company_dirs = [d for d in companies_dir.iterdir() if d.is_dir()]
    if not company_dirs:
        console.print("[yellow]No companies found.[/yellow]")
        return

    sorted_dirs = sorted(company_dirs, key=lambda d: d.stat().st_ctime, reverse=True)

    console.print("[bold]Most recently created companies:[/bold]")
    for i, company_dir in enumerate(sorted_dirs):
        if i >= count:
            break
        console.print(f"- {company_dir.name}")


@app.command("backfill-from-prospects")
def backfill_from_prospects(
    campaign: str = typer.Option(
        ..., "--campaign", "-c", help="Campaign whose prospects checkpoint to backfill from."
    ),
    execute: bool = typer.Option(
        False,
        "--execute",
        help="Actually create the company directories. Without this flag, only reports what would be created.",
    ),
    min_hours_since_last_run: Optional[float] = typer.Option(
        None,
        "--min-hours-since-last-run",
        help=(
            "With --execute, skip entirely if a previous --execute run for this "
            "campaign completed less than this many hours ago (tracked via a marker "
            "file, not a fixed schedule - for a login-triggered scheduled run rather "
            "than a fixed calendar time). Ignored for dry runs, which always show live state."
        ),
    ),
) -> None:
    """
    Materializes companies/<slug> directories for prospects that exist in a
    campaign's prospects checkpoint but were never compiled into a company
    record. Defaults to a dry run; pass --execute to write.
    """
    from ..application.company_service import backfill_missing_companies_from_prospects

    result = backfill_missing_companies_from_prospects(
        campaign, dry_run=not execute, min_hours_since_last_run=min_hours_since_last_run
    )

    if result.get("skipped_stale_check"):
        console.print(
            f"[yellow]Skipped - last --execute run for '{campaign}' was "
            f"{result['hours_since_last_run']:.1f}h ago, under the "
            f"{result['min_hours_since_last_run']}h threshold.[/yellow]"
        )
        return

    console.print(f"[bold]Campaign:[/bold] {result['campaign_name']}")
    console.print(f"[bold]Existing companies (data-root wide):[/bold] {result['existing_company_count']}")
    console.print(f"[bold]Prospects with no company directory:[/bold] {result['missing_count']}")
    if execute:
        console.print(f"[bold green]Created:[/bold green] {result['created_count']} (tag: {result['tag']})")
    else:
        console.print(
            f"[yellow]Dry run - no files written. Re-run with --execute to create "
            f"{result['missing_count']} companies tagged '{campaign}' and '{result['tag']}'.[/yellow]"
        )
