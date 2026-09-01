"""CLI adapter for campaign management commands."""

from __future__ import annotations

import asyncio
import logging
import subprocess
from typing import Any, Dict, Optional

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table
from typing_extensions import Annotated

from ...application.campaign_service import CampaignService
from ...core.campaign_workflow import CampaignWorkflow
from ...core.config import get_campaign, get_editor_command
from ...core.utils import run_fzf
from ...renderers.campaign_view import display_campaign_view

logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer(no_args_is_help=True)


def _require_campaign(campaign_name: Optional[str]) -> str:
    name = campaign_name or get_campaign()
    if not name:
        console.print("[bold red]Error: No campaign specified.[/bold red]")
        raise typer.Exit(1)
    return name


@app.command()
def edit(
    campaign_name: Annotated[
        Optional[str], typer.Argument(help="The name of the campaign to edit.")
    ] = None,
) -> None:
    """
    Edits an existing campaign's configuration.
    """
    if campaign_name is None:
        campaign_names = CampaignService.list_campaign_names()
        if not campaign_names:
            console.print("[bold red]No campaigns found.[/bold red]")
            raise typer.Exit(code=1)

        selected_campaign = run_fzf("\n".join(campaign_names))
        if not selected_campaign:
            console.print("No campaign selected.")
            raise typer.Exit(code=1)
        campaign_name = selected_campaign

    try:
        targets = CampaignService(campaign_name).get_edit_targets()
    except FileNotFoundError as e:
        console.print(f"[bold red]{e}[/bold red]")
        raise typer.Exit(code=1)

    if not targets.config_exists:
        console.print(
            f"[bold red]Configuration file not found for campaign "
            f"'{campaign_name}'.[/bold red]"
        )

    editor_command = get_editor_command()
    if editor_command:
        command = [editor_command]
        if "vim" in editor_command or "nvim" in editor_command:
            command.append("-o")
        command.extend(str(p) for p in targets.files_to_edit)
        subprocess.run(command)
        return

    if targets.config_exists:
        typer.edit(filename=str(targets.config_path))
    else:
        console.print(
            f"[bold red]Configuration file not found for campaign "
            f"'{campaign_name}'.[/bold red]"
        )

    if targets.readme_exists:
        console.print(
            "[yellow]To edit the README.md as well, please configure an editor "
            "in your cocli_config.toml.[/yellow]"
        )


@app.command()
def add(
    name: Annotated[str, typer.Argument(help="The name of the campaign.")],
    company: Annotated[str, typer.Argument(help="The name of the company.")],
) -> None:
    """
    Adds a new campaign.
    """
    try:
        CampaignService.create_campaign(name, company)
        console.print(f"[green]Campaign '{name}' created successfully.[/green]")
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]An unexpected error occurred: {e}[/red]")
        raise typer.Exit(code=1)


@app.command(name="set", no_args_is_help=True)
def set_default_campaign(
    campaign_name: str = typer.Argument(
        ..., help="The name of the campaign to set as the current context."
    ),
) -> None:
    """Sets the current campaign context."""
    try:
        service = CampaignService(campaign_name)
        service.activate()
        # Workflow still imports command modules (burn-down); keep out of CampaignService
        # so TUI -> application does not transitively import commands.
        workflow = CampaignWorkflow(campaign_name)
        console.print(f"[green]Campaign context set to:[/][bold]{campaign_name}[/]")
        console.print(
            f"[green]Current workflow state for '{campaign_name}':[/]"
            f"[bold]{workflow.state}[/]"
        )
    except Exception as e:
        console.print(f"[red]Error setting campaign: {e}[/red]")
        raise typer.Exit(code=1)


@app.command()
def unset() -> None:
    """
    Clears the current campaign context.
    """
    CampaignService.clear_context()
    console.print("[green]Campaign context cleared.[/]")


@app.command("list")
def list_campaigns(
    paths: bool = typer.Option(
        False,
        "--paths",
        help="Include the absolute campaign directory path column.",
    ),
) -> None:
    """List local campaigns with descriptions.

    Description comes from ``[campaign].description`` in config.toml when set,
    otherwise the first prose paragraph of README.md, otherwise tag/domain.
    """
    items = CampaignService.list_campaigns()
    if not items:
        console.print("[yellow]No campaigns found.[/yellow]")
        return

    table = Table(title="Local campaigns", show_lines=False)
    table.add_column("", width=1, no_wrap=True)  # active marker
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Tag", style="dim")
    table.add_column("Domain", style="dim")
    table.add_column("Description")
    if paths:
        table.add_column("Path", style="dim")

    for item in items:
        marker = "*" if item.active else ""
        row = [
            marker,
            item.name,
            item.tag or "",
            item.domain or "",
            item.description or "",
        ]
        if paths:
            row.append(str(item.path))
        table.add_row(*row)

    console.print(table)
    active = next((i.name for i in items if i.active), None)
    if active:
        console.print(f"[dim]* active context: {active}[/dim]")


@app.command()
def show() -> None:
    """
    Displays the current campaign context.
    """
    campaign_name = get_campaign()
    if not campaign_name:
        console.print("No campaign context is set.")
        return

    try:
        campaign = CampaignService(campaign_name).load_campaign_model()
    except FileNotFoundError as e:
        console.print(f"[bold red]{e}[/bold red]")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(
            f"[bold red]Error validating campaign configuration for "
            f"'{campaign_name}': {e}[/bold red]"
        )
        raise typer.Exit(code=1)

    display_campaign_view(console, campaign)


@app.command()
def status(
    campaign_name: Optional[str] = typer.Argument(
        None,
        help="Name of the campaign to show status for. If not provided, uses the current campaign context.",
    ),
) -> None:
    """
    Displays the current state of the campaign workflow.
    """
    effective = campaign_name or get_campaign()
    if effective is None:
        console.print(
            "[bold red]Error: No campaign name provided and no campaign context "
            "is set. Please provide a campaign name or set a campaign context "
            "using 'cocli campaign set <campaign_name>'.[/bold red]"
        )
        raise typer.Exit(code=1)

    workflow = CampaignWorkflow(effective)
    console.print(
        f"[green]Current workflow state for '{effective}':[/]"
        f"[bold]{workflow.state}[/]"
    )


@app.command()
def add_query(
    query: Annotated[str, typer.Argument(help="The search query to add.")],
    campaign_name: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name."
    ),
) -> None:
    """Adds a search query to the campaign configuration."""
    name = _require_campaign(campaign_name)
    try:
        if CampaignService(name).add_query(query):
            console.print(f"[green]Added query:[/green] {query}")
        else:
            console.print(f"[yellow]Query already exists:[/yellow] {query}")
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1)


@app.command()
def remove_query(
    query: Annotated[str, typer.Argument(help="The search query to remove.")],
    campaign_name: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name."
    ),
) -> None:
    """Removes a search query from the campaign configuration."""
    name = _require_campaign(campaign_name)
    try:
        if CampaignService(name).remove_query(query):
            console.print(f"[green]Removed query:[/green] {query}")
        else:
            console.print(f"[yellow]Query not found:[/yellow] {query}")
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1)


@app.command()
def add_location(
    location: Annotated[str, typer.Argument(help="The location name/city to add.")],
    campaign_name: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name."
    ),
) -> None:
    """Adds a target location to the campaign."""
    name = _require_campaign(campaign_name)
    try:
        if CampaignService(name).add_location(location):
            console.print(f"[green]Added location:[/green] {location}")
        else:
            console.print(f"[yellow]Location already exists:[/yellow] {location}")
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1)


@app.command()
def remove_location(
    location: Annotated[str, typer.Argument(help="The location name/city to remove.")],
    campaign_name: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name."
    ),
) -> None:
    """Removes a target location from the campaign."""
    name = _require_campaign(campaign_name)
    try:
        if CampaignService(name).remove_location(location):
            console.print(f"[green]Removed location:[/green] {location}")
        else:
            console.print(f"[yellow]Location not found:[/yellow] {location}")
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1)


@app.command()
def geocode_locations(
    campaign_name: Annotated[
        Optional[str], typer.Argument(help="The name of the campaign.")
    ] = None,
) -> None:
    """
    Scans the campaign's target locations CSV and fills in missing geocoordinates.
    """
    name = _require_campaign(campaign_name)
    try:
        updated_count = CampaignService(name).geocode_locations()
        if updated_count > 0:
            console.print(
                f"[bold green]Successfully updated {updated_count} locations."
                f"[/bold green]"
            )
        else:
            console.print("[yellow]No locations were updated.[/yellow]")
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1)


@app.command()
def bucket(
    campaign_name: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name."
    ),
) -> None:
    """
    Displays the S3 bucket root and campaign path.
    """
    name = _require_campaign(campaign_name)
    try:
        uri = CampaignService(name).get_s3_campaign_uri()
    except FileNotFoundError as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1)
    console.print(uri)


@app.command(name="compile-lifecycle")
def compile_lifecycle(
    campaign_name: Annotated[
        Optional[str], typer.Argument(help="The name of the campaign.")
    ] = None,
) -> None:
    """
    Compiles the lifecycle index from local completed queues.
    Mandate: Sync 'queues/' before running.
    """
    name = _require_campaign(campaign_name)
    try:
        service = CampaignService(name)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("[dim]{task.fields[label]}"),
            console=console,
        ) as progress:
            task = progress.add_task(
                "Compiling lifecycle index...", total=None, label=""
            )
            final_count = 0
            for update in service.compile_lifecycle_index():
                if isinstance(update, dict):
                    progress.update(
                        task,
                        description=f"Compiling: {update['phase']}",
                        total=update["total"],
                        completed=update["current"],
                        label=update["label"],
                    )
                else:
                    final_count = update

        console.print(
            f"[bold green]Successfully compiled lifecycle index with "
            f"{final_count} records.[/bold green]"
        )
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1)


@app.command(name="restore-names")
def restore_names(
    campaign_name: Annotated[
        Optional[str], typer.Argument(help="The name of the campaign.")
    ] = None,
    dry_run: bool = typer.Option(False, "--dry-run", help="Don't save changes."),
) -> None:
    """
    Restores company names from the Google Maps index and writes provenance receipts.
    """
    name = _require_campaign(campaign_name)
    try:
        service = CampaignService(name)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("[dim]{task.fields[slug]}"),
            console=console,
        ) as progress:
            task = progress.add_task("Restoring names...", total=None, slug="")
            final_stats: Dict[str, Any] = {}
            for update in service.restore_names_from_index(dry_run=dry_run):
                if "total" in update:
                    progress.update(
                        task,
                        total=update["total"],
                        completed=update["current"],
                        slug=update["slug"],
                    )
                else:
                    final_stats = update

        if dry_run:
            console.print(
                f"[yellow]DRY RUN: Would restore "
                f"{final_stats.get('restored', 0)} names.[/yellow]"
            )
        else:
            console.print(
                f"[bold green]Successfully restored "
                f"{final_stats.get('restored', 0)} names.[/bold green]"
            )
            console.print(
                f"[bold green]Wrote {final_stats.get('receipts_written', 0)} "
                f"provenance receipts.[/bold green]"
            )

        if final_stats.get("errors", 0) > 0:
            console.print(
                f"[bold red]Encoutered {final_stats['errors']} errors.[/bold red]"
            )
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1)


@app.command(name="sanitize-discovery")
def sanitize_discovery(
    campaign_name: Annotated[
        Optional[str], typer.Argument(help="The name of the campaign.")
    ] = None,
) -> None:
    """
    High-Fidelity Discovery Reset: Pulls from S3, purges junk/hollow USVs, and propagates to PIs.
    """
    name = _require_campaign(campaign_name)
    try:
        from ...application.operation_service import OperationService

        service = OperationService(name)
        console.print(
            f"[bold cyan]Starting Discovery Sanitization for: {name}[/bold cyan]"
        )

        def log_cb(msg: str) -> None:
            console.print(f"  {msg.strip()}")

        async def run_op() -> Dict[str, Any]:
            return await service.execute(
                "op_sanitize_discovery", log_callback=log_cb
            )

        result = asyncio.run(run_op())
        if result["status"] == "success":
            console.print(
                f"\n[bold green]Successfully sanitized discovery for "
                f"'{name}'.[/bold green]"
            )
        else:
            console.print(
                f"\n[bold red]Sanitization failed: "
                f"{result.get('message')}[/bold red]"
            )
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1)


@app.command(name="compile-to-call")
def compile_to_call(
    campaign_name: Annotated[
        Optional[str], typer.Argument(help="The name of the campaign.")
    ] = None,
    limit: int = typer.Option(50, help="Number of top leads to tag for calling."),
    purge: bool = typer.Option(
        False,
        "--purge",
        help="Clear the existing pending to-call queue before repopulating.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview what would happen (companies created/updated, tasks enqueued) without writing anything - skips compaction, company writes, --purge, and the queue write.",
    ),
) -> None:
    """
    Compiles prospects to a To-Call list. "Add more" (no --purge) is the
    standard way to run this - it never re-adds a slug already pending and
    never adds anyone on the shared do-not-call list, so it's safe to run
    repeatedly as new leads come in without disturbing what's already queued
    or dispositioned:

    1. Consolidates GM results and compacts index.
    2. Compacts email index.
    3. Identifies top leads: ranked by rating x review count (descending),
       must have both a rating and a review count on record, plus contact
       info (email or phone) - no artificial rating/review-count cutoff, so
       the best available candidates surface even in thinner markets.
       Excludes companies on the exclusion list (per-campaign or shared/
       global, `cocli exclude`) and anyone whose phone is on the shared
       do-not-call list (`cocli do-not-call`).
    4. (Optional, --purge) Clears the existing pending to-call queue.
    5. Adds top leads to the 'to-call' queue - skips any candidate already
       pending (no wasted rewrite) or on the do-not-call list.

    --dry-run runs step 3 for real (read-only) and reports what steps 1, 2,
    4, and 5 would do, without writing anything - useful as a smoke test
    before a full run, especially paired with --limit for a quick check.
    """
    name = _require_campaign(campaign_name)
    try:
        from ...application.operation_service import OperationService
        from .._operation_console import operation_log_callback, print_operation_steps

        service = OperationService(name)
        console.print(
            f"[bold cyan]{'Previewing' if dry_run else 'Compiling'} To-Call list for: {name}[/bold cyan]"
        )
        meta = service.get_details("op_compile_to_call")
        if meta:
            print_operation_steps(console, meta)

        log_cb = operation_log_callback(console)

        async def run_op() -> Dict[str, Any]:
            return await service.execute(
                "op_compile_to_call",
                log_callback=log_cb,
                params={"limit": limit, "purge": purge, "dry_run": dry_run},
            )

        result = asyncio.run(run_op())
        if result["status"] == "success":
            op_result = result.get("result", {})
            if op_result.get("dry_run"):
                console.print(
                    f"\n[bold]Dry run - nothing written.[/bold] Would create "
                    f"{op_result.get('would_create_count', 0)} companies, update "
                    f"{op_result.get('would_update_count', 0)}, enqueue "
                    f"{op_result.get('would_enqueue_count', 0)} to-call tasks "
                    f"(skipped {op_result.get('skipped_already_pending', 0)} already "
                    f"pending, {op_result.get('skipped_do_not_call', 0)} do-not-call)."
                )
                sample = op_result.get("sample_slugs") or []
                if sample:
                    console.print(f"  Sample: {', '.join(sample)}")
            else:
                console.print(
                    f"\n[bold green]Successfully compiled To-Call list for "
                    f"'{name}'.[/bold green] Enqueued {op_result.get('created_count', 0)} "
                    f"(skipped {op_result.get('skipped_already_pending', 0)} already "
                    f"pending, {op_result.get('skipped_do_not_call', 0)} do-not-call)."
                )
        else:
            console.print(
                f"\n[bold red]Compile failed: {result.get('message')}[/bold red]"
            )
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1)


@app.command(name="path-check")
def path_check(
    paths: Annotated[
        str,
        typer.Argument(
            help="Comma-separated list of path templates (use {campaign} placeholder)."
        ),
    ],
    campaigns: Annotated[
        Optional[str],
        typer.Option(
            "--campaigns", "-c", help="Comma-separated list of campaigns to audit."
        ),
    ] = None,
) -> None:
    """
    Audits specific data paths across the local machine, PI cluster, and S3.
    """
    effective_campaign = get_campaign()
    campaign_list = (
        [c.strip() for c in campaigns.split(",")]
        if campaigns
        else ([effective_campaign] if effective_campaign else [])
    )

    if not campaign_list:
        console.print(
            "[bold red]Error: No campaigns specified and no active context.[/bold red]"
        )
        raise typer.Exit(1)

    path_list = [p.strip() for p in paths.split(",")]

    try:
        from ...application.services import ServiceContainer

        services = ServiceContainer(campaign_name=campaign_list[0])
        results = services.cluster_audit_service.audit_cluster_paths(
            path_list, campaigns=campaign_list
        )

        table = Table(title="Cluster Path Audit")
        table.add_column("Campaign", style="cyan")
        table.add_column("Path Template", style="magenta")
        table.add_column("Location", style="yellow")
        table.add_column("Status", justify="center")

        for r in results:
            status_style = "green" if r["status"] == "FOUND" else "red"
            if r["status"] == "NO BUCKET":
                status_style = "yellow"
            table.add_row(
                r["campaign"],
                r["template"],
                r["location"],
                f"[{status_style}]{r['status']}[/]",
            )
        console.print(table)
    except Exception as e:
        console.print(f"[bold red]Error during path audit: {e}[/bold red]")
        raise typer.Exit(1)
