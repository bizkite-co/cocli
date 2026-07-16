# POLICY: frictionless-data-policy-enforcement
"""CLI adapter for campaign rollout management."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from cocli.application.deployment_service import DeploymentService
from cocli.application.operation_service import OperationService
from cocli.core.config import get_campaign

logger = logging.getLogger(__name__)
console = Console()
app = typer.Typer(
    name="rollout",
    help="Standardized campaign rollout management.",
    no_args_is_help=True,
)


def _require_campaign(campaign_name: Optional[str]) -> str:
    name = campaign_name or get_campaign()
    if not name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)
    return name


@app.command(name="run")
def run_rollout(
    campaign_name: Annotated[
        Optional[str], typer.Argument(help="The name of the campaign.")
    ] = None,
    name: str = typer.Option(
        "canary", help="Name of the batch (e.g., 'canary', 'rollout_1')"
    ),
    limit: int = typer.Option(50, help="Number of items to include in the batch"),
    ttl_days: int = typer.Option(
        30,
        help="Items scraped longer than this many days ago are considered stale.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force rescrape of all items in the batch (sets TTL to 0).",
    ),
    purge: bool = typer.Option(
        False,
        "--purge",
        help="Purge the existing active task pool before starting (Clean Start).",
    ),
    monitor: bool = typer.Option(
        True,
        "--monitor/--no-monitor",
        help="Automatically start monitoring after rollout.",
    ),
) -> None:
    """
    Executes a standardized discovery rollout:
    1. Create Batch -> 2. Build Mission Index -> 3. Push to Cluster
    """
    campaign = _require_campaign(campaign_name)
    effective_ttl = 0 if force else ttl_days
    op_service = OperationService(campaign)

    async def run() -> None:
        params = {
            "batch_name": name,
            "limit": limit,
            "ttl_days": effective_ttl,
            "purge": purge,
        }

        def log_cb(msg: str) -> None:
            console.print(msg, end="")

        result = await op_service.execute(
            "op_rollout_discovery", log_callback=log_cb, params=params
        )

        if result["status"] == "success":
            console.print(f"\n[bold green]Rollout '{name}' successful![/bold green]")
            if monitor:
                console.print(
                    f"[cyan]Starting cluster monitor for batch: {name}...[/cyan]"
                )
                console.print(
                    f"\nRun: [bold white]cocli campaign monitor-batch "
                    f"{campaign} --name {name} --cluster[/bold white]"
                )
        else:
            console.print(
                f"\n[bold red]Rollout failed: {result.get('message')}[/bold red]"
            )

    asyncio.run(run())


@app.command(name="broadcast-config")
def broadcast_config(
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name."
    ),
) -> None:
    """
    Broadcasts the current scaling configuration to all cluster nodes via Gossip.
    Triggers near-instantaneous worker re-balancing.
    """
    effective_campaign = _require_campaign(campaign)
    service = DeploymentService(effective_campaign)

    def log_cb(msg: str) -> None:
        console.print(f"[bold cyan]{msg}[/bold cyan]")

    try:
        result = service.broadcast_scaling_config(
            campaign_name=effective_campaign, log_callback=log_cb
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    if not result.scaling:
        console.print(f"[yellow]{result.message}[/yellow]")
        return

    console.print(f"[bold green]{result.message}[/bold green]")


@app.command(name="push-config")
def push_config(
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name."
    ),
) -> None:
    """
    Uploads the local campaign config.toml to S3 (campaigns/{campaign}/config.toml).

    This is the source of truth Fargate tasks pull from at startup, since the
    Fargate image does not bundle the data/ directory and cannot reach the
    Pis' rsync-based config distribution. Run this after any change to
    [prospecting.scaling] (or other config) that Fargate workers need to see.
    """
    effective_campaign = _require_campaign(campaign)
    service = DeploymentService(effective_campaign)
    try:
        result = service.push_config_to_s3(campaign_name=effective_campaign)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    console.print(f"[bold green]{result.message}[/bold green]")


@app.command(name="pull-config")
def pull_config(
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name."
    ),
) -> None:
    """
    Downloads campaign config.toml from S3 to local disk (campaigns/{campaign}/config.toml).

    Called by the Fargate container's entrypoint before starting the worker
    orchestrator, since load_campaign_config() only ever reads from local disk
    and the Fargate image doesn't bundle data/. On Fargate this uses the ECS
    Task Role (no profile) via COCLI_RUNNING_IN_FARGATE, matching the pattern
    already used in cocli/core/queue/factory.py.
    """
    effective_campaign = _require_campaign(campaign)
    service = DeploymentService(effective_campaign)
    result = service.pull_config_from_s3(campaign_name=effective_campaign)

    if result.warning:
        console.print(f"[bold yellow]{result.message}[/bold yellow]")
    else:
        console.print(f"[bold green]{result.message}[/bold green]")


@app.command(name="push")
def push_data(
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name."
    ),
    delete: bool = typer.Option(
        False, "--delete", help="Delete remote files not present locally."
    ),
) -> None:
    """
    Propagates local campaign discovery tasks and batches to the cluster.
    (Moved from 'cluster push-data' for campaign-centric workflow)
    """
    effective_campaign = _require_campaign(campaign)
    service = DeploymentService(effective_campaign)

    async def run() -> None:
        await service.push_discovery_data(delete=delete)
        console.print("[bold green]Data propagated to cluster.[/bold green]")

    asyncio.run(run())


@app.command(name="audit")
def sync_audit(
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name."
    ),
) -> None:
    """
    Pulls results from all cluster nodes and runs a quality audit.
    (Moved from 'cluster sync-audit' for campaign-centric workflow)
    """
    effective_campaign = _require_campaign(campaign)
    service = DeploymentService(effective_campaign)

    async def run() -> None:
        await service.sync_and_audit_cluster()

    asyncio.run(run())


@app.command(name="status")
def rollout_status(
    campaign_name: Annotated[
        Optional[str], typer.Argument(help="Campaign name")
    ] = None,
) -> None:
    """
    Show current rollout status: batches deployed, and synced results.
    """
    campaign = _require_campaign(campaign_name)
    diagnostics = DeploymentService(campaign).get_rollout_diagnostics(campaign)

    console.print(f"\n[bold blue]Rollout Status: {campaign}[/bold blue]")
    console.print(f"[dim]{'─' * 70}[/dim]")

    if diagnostics.batches:
        batch_table = Table(title="Batches Deployed")
        batch_table.add_column("Batch Name", style="cyan")
        batch_table.add_column("Tasks", style="yellow")

        for batch_name, task_count in sorted(diagnostics.batches.items()):
            batch_table.add_row(batch_name, str(task_count))

        console.print(batch_table)
        console.print(
            f"[bold]Total Deployed: {diagnostics.total_tasks} tasks[/bold]\n"
        )
    else:
        console.print("[yellow]No batches deployed[/yellow]\n")

    console.print("[bold]Results Synced to Hub:[/bold]")
    console.print(
        f"  Unique Companies: [green]{diagnostics.hub_companies:,}[/green]"
    )
    if diagnostics.batches and diagnostics.total_tasks > 0:
        console.print(
            f"  Avg per Task: [cyan]{diagnostics.avg_per_task:.1f}[/cyan]"
        )

    console.print(f"[dim]{'─' * 70}[/dim]")
    console.print(
        "[dim]Run [bold]cocli campaign rollout sync[/bold] to pull latest "
        "results from S3[/dim]\n"
    )


@app.command(name="progress")
def rollout_progress(
    campaign_name: Annotated[
        Optional[str], typer.Argument(help="Campaign name")
    ] = None,
    watch: Annotated[
        bool,
        typer.Option(
            "--watch", "-w", help="Continuously monitor (updates every 10s)"
        ),
    ] = False,
) -> None:
    """
    Show real-time progress of active rollout.
    Reports synced results from hub. Run 'cocli campaign rollout sync' first for latest data.
    """
    campaign = _require_campaign(campaign_name)
    service = DeploymentService(campaign)

    def show_progress() -> None:
        diagnostics = service.get_rollout_diagnostics(campaign)

        if diagnostics.total_tasks == 0:
            console.print("[yellow]No batches deployed[/yellow]")
            return

        console.print(
            f"[bold]Progress:[/bold] {diagnostics.hub_companies:,} companies "
            f"from {diagnostics.total_tasks} tasks | "
            f"{diagnostics.avg_per_task:.1f} avg/task"
        )

    if watch:
        while True:
            console.clear()
            show_progress()
            console.print(
                "\n[dim]Syncing every 30 seconds... (press Ctrl+C to stop)[/dim]"
            )
            time.sleep(30)
    else:
        show_progress()


@app.command(name="sync")
def rollout_sync(
    campaign_name: Annotated[
        Optional[str], typer.Argument(help="Campaign name")
    ] = None,
    deduplicate: Annotated[
        bool,
        typer.Option(
            "--deduplicate", help="Remove duplicate companies across PIs"
        ),
    ] = True,
    workers: int = typer.Option(
        20, help="Number of concurrent download threads"
    ),
    full: bool = typer.Option(
        False, "--full", help="Perform a full sync (slower)"
    ),
    force: bool = typer.Option(
        False, "--force", help="Force re-download all files"
    ),
) -> None:
    """
    Sync scraping results from PIs back to hub via S3.
    Deduplicates companies by place_id across all nodes.
    """
    campaign = _require_campaign(campaign_name)
    service = DeploymentService(campaign)

    def log_cb(msg: str) -> None:
        if msg.startswith("Step "):
            console.print(f"[yellow]{msg}[/yellow]")
        elif msg.startswith("Syncing results"):
            console.print(f"[bold cyan]{msg}[/bold cyan]")
        else:
            console.print(msg)

    # `deduplicate` retained for CLI compatibility; service always computes
    # place_id uniqueness stats (same as original implementation).
    _ = deduplicate

    result = service.sync_rollout_results(
        campaign_name=campaign,
        workers=workers,
        full=full,
        force=force,
        log_callback=log_cb,
    )

    console.print(f"\n[bold blue]{result.message}[/bold blue]")
    console.print(f"[dim]{'─' * 70}[/dim]")
    console.print(f"  Tasks Deployed: [cyan]{result.total_tasks_deployed}[/cyan]")
    console.print(
        f"  Unique Companies Found: [green]{result.unique_companies:,}[/green]"
    )
    if result.duplicates > 0:
        console.print(
            f"  Duplicate Entries Across PIs: [yellow]{result.duplicates:,}[/yellow]"
        )
    if result.total_tasks_deployed > 0:
        console.print(
            f"  Avg Companies/Task: [cyan]{result.avg_companies_per_task:.1f}[/cyan]"
        )
    console.print(f"[dim]{'─' * 70}[/dim]\n")


@app.command(name="report")
def rollout_report(
    campaign_name: Annotated[
        Optional[str], typer.Argument(help="Campaign name")
    ] = None,
) -> None:
    """
    Detailed audit report: batches, coverage, and synced results.
    """
    campaign = _require_campaign(campaign_name)
    diagnostics = DeploymentService(campaign).get_rollout_diagnostics(campaign)

    console.print(f"\n[bold blue]Rollout Report: {campaign}[/bold blue]")
    console.print(f"[dim]{'─' * 70}[/dim]")

    console.print("\n[bold]Deployment Coverage:[/bold]")
    console.print(f"  Batches: {len(diagnostics.batches)}")
    for batch_name, task_count in sorted(diagnostics.batches.items()):
        console.print(f"    {batch_name}: {task_count} tasks")
    console.print(f"  Total Deployed: {diagnostics.total_tasks} tasks")

    console.print("\n[bold]Results (Synced & Deduplicated):[/bold]")
    console.print(f"  Unique Companies: {diagnostics.hub_companies:,}")
    if diagnostics.total_tasks > 0:
        console.print(f"  Avg per Task: {diagnostics.avg_per_task:.1f}")

    console.print(
        f"  Coverage Estimate: {diagnostics.coverage_estimate_pct:.0f}%"
    )

    console.print(
        "\n[dim]Last synced: Run [bold]cocli campaign rollout sync[/bold] "
        "to update[/dim]"
    )
    console.print(f"[dim]{'─' * 70}[/dim]\n")


if __name__ == "__main__":
    app()
