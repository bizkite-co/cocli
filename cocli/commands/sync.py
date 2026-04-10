import typer
from typing import Optional
from rich.console import Console
from ..services.sync_service import SyncService

console = Console()
app = typer.Typer(help="Commands for syncing data with S3.")


@app.command()
def queue(
    campaign_name: str = typer.Argument(..., help="The campaign name."),
    queue_name: str = typer.Argument(
        ..., help="The queue name (e.g., enrichment, gm-details)."
    ),
    direction: str = typer.Option(
        "up", "--direction", help="Direction: 'up' (Local->S3) or 'down' (S3->Local)."
    ),
    delete: bool = typer.Option(
        False, "--delete", help="Delete missing files on destination."
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-l", help="Limit sync to first N shards."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done."),
) -> None:
    """
    Syncs a specific campaign queue with S3.
    """
    try:
        service = SyncService(campaign_name)
        console.print(
            f"[bold blue]Syncing Queue: {queue_name} for {campaign_name}[/bold blue]"
        )
        console.print(f"  Bucket:  {service.bucket}")
        console.print(f"  Profile: {service.profile or 'default'}")

        # Validate direction
        if direction not in ["up", "down"]:
            console.print("[red]Error: Direction must be 'up' or 'down'[/red]")
            raise typer.Exit(1)

        service.sync_queue(
            queue_name=queue_name,
            direction=direction,  # type: ignore
            delete=delete,
            limit=limit,
            dry_run=dry_run,
        )
        console.print("[bold green]Queue Sync Complete![/bold green]")
    except Exception as e:
        console.print(f"[bold red]Sync Failed:[/bold red] {e}")
        raise typer.Exit(1)


@app.command()
def indexes(
    campaign_name: Optional[str] = typer.Argument(
        None,
        help="The campaign name to sync. Defaults to current context if not provided.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be synced without actually doing it."
    ),
) -> None:
    """
    Bidirectional sync of indexes with S3.
    """
    from cocli.core.config import get_campaign

    if not campaign_name:
        campaign_name = get_campaign()

    if not campaign_name:
        console.print(
            "[bold red]No campaign specified and no active campaign found. Cannot sync.[/bold red]"
        )
        raise typer.Exit(1)

    try:
        service = SyncService(campaign_name)
        console.print(
            f"[bold blue]Syncing Campaign '{campaign_name}' Indexes...[/bold blue]"
        )
        service.sync_indexes(dry_run=dry_run)
        console.print("[bold green]Index Sync Complete![/bold green]")
    except Exception as e:
        console.print(f"[bold red]Sync Failed:[/bold red] {e}")
        raise typer.Exit(1)


@app.command()
def config(
    campaign_name: str = typer.Argument(..., help="The campaign name."),
    direction: str = typer.Option(
        "up", "--direction", help="Direction: 'up' (Local->S3) or 'down' (S3->Local)."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done."),
) -> None:
    """
    Syncs the campaign config.toml file with S3.
    """
    try:
        service = SyncService(campaign_name)
        console.print(f"[bold blue]Syncing Config for {campaign_name}[/bold blue]")
        console.print(f"  Bucket:  {service.bucket}")

        # Validate direction
        if direction not in ["up", "down"]:
            console.print("[red]Error: Direction must be 'up' or 'down'[/red]")
            raise typer.Exit(1)

        service.sync_config(
            direction=direction,  # type: ignore
            dry_run=dry_run,
        )
        console.print("[bold green]Config Sync Complete![/bold green]")
    except Exception as e:
        console.print(f"[bold red]Sync Failed:[/bold red] {e}")
        raise typer.Exit(1)


@app.command()
def pi_results(
    campaign: str | None = typer.Option(
        None, "--campaign", "-c", help="The campaign name. Defaults to current context."
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force sync ignoring timestamp."
    ),
    status: bool = typer.Option(False, "--status", "-s", help="Show sync status only."),
) -> None:
    """
    Sync gm-list results from Pi workers.

    This command syncs the latest scraping results from configured Pi workers
    to the local campaign data directory. Results are stored in:
        queues/gm-list/completed/results/

    Usage:
        cocli sync pi-results --campaign roadmap       # Sync if stale
        cocli sync pi-results --campaign roadmap --force  # Force sync
        cocli sync pi-results --status                   # Check status
    """
    from cocli.core.config import get_campaign
    from cocli.core.sync_tracker import SyncTracker
    from cocli.application.pi_sync_service import PiSyncService

    # Default to "roadmap" if no campaign is active, as a safe fallback for cluster-wide syncing
    campaign_name = campaign or get_campaign() or "roadmap"

    tracker = SyncTracker(campaign_name)
    service = PiSyncService(campaign_name)

    if status:
        last_sync = tracker.get_last_sync()
        if last_sync:
            from datetime import datetime, UTC

            age = datetime.now(UTC) - last_sync
            age_minutes = age.total_seconds() / 60
            console.print(
                f"[blue]Last sync:[/blue] {last_sync.isoformat()} ({age_minutes:.0f} minutes ago)"
            )
            if tracker.needs_sync():
                console.print("[yellow]Sync is STALE (>1 hour)[/yellow]")
            else:
                console.print("[green]Sync is current[/green]")
        else:
            console.print("[yellow]Never synced[/yellow]")
        return

    if force or tracker.needs_sync():
        console.print(
            f"[bold blue]Syncing PI results for campaign: {campaign_name}[/bold blue]"
        )
        results = service.sync_all_nodes(blocking=True)
        summary = service.get_summary()

        console.print("[blue]Results:[/blue]")
        console.print(
            f"  Nodes: {summary['successful']}/{summary['total_nodes']} successful"
        )
        console.print(f"  Files: {summary['total_files_synced']} synced")

        if summary["failed"] > 0:
            console.print("[yellow]Failed nodes:[/yellow]")
            for r in results:
                if not r.success:
                    console.print(f"  - {r.host}: {r.error}")
            console.print("[bold red]Sync completed with errors[/bold red]")
            raise typer.Exit(1)
        else:
            tracker.update_last_sync()
            console.print("[bold green]Sync Complete![/bold green]")
    else:
        console.print("[green]Sync not needed (recently synced)[/green]")
