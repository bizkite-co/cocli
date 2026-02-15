import typer
from typing import Optional
from rich.console import Console
from ..services.sync_service import SyncService

console = Console()
app = typer.Typer(help="Commands for syncing data with S3.")

@app.command()
def queue(
    campaign_name: str = typer.Argument(..., help="The campaign name."),
    queue_name: str = typer.Argument(..., help="The queue name (e.g., enrichment, gm-details)."),
    direction: str = typer.Option("up", "--direction", help="Direction: 'up' (Local->S3) or 'down' (S3->Local)."),
    delete: bool = typer.Option(False, "--delete", help="Delete missing files on destination."),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Limit sync to first N shards."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done.")
) -> None:
    """
    Syncs a specific campaign queue with S3.
    """
    try:
        service = SyncService(campaign_name)
        console.print(f"[bold blue]Syncing Queue: {queue_name} for {campaign_name}[/bold blue]")
        console.print(f"  Bucket:  {service.bucket}")
        console.print(f"  Profile: {service.profile or 'default'}")
        
        # Validate direction
        if direction not in ["up", "down"]:
            console.print("[red]Error: Direction must be 'up' or 'down'[/red]")
            raise typer.Exit(1)
            
        service.sync_queue(
            queue_name=queue_name,
            direction=direction, # type: ignore
            delete=delete,
            limit=limit,
            dry_run=dry_run
        )
        console.print("[bold green]Queue Sync Complete![/bold green]")
    except Exception as e:
        console.print(f"[bold red]Sync Failed:[/bold red] {e}")
        raise typer.Exit(1)

@app.command()
def indexes(
    campaign_name: Optional[str] = typer.Argument(None, help="The campaign name to sync. Defaults to current context if not provided."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be synced without actually doing it."),
) -> None:
    """
    Bidirectional sync of indexes with S3.
    """
    from cocli.core.config import get_campaign
    
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[bold red]No campaign specified and no active campaign found. Cannot sync.[/bold red]")
        raise typer.Exit(1)

    try:
        service = SyncService(campaign_name)
        console.print(f"[bold blue]Syncing Campaign '{campaign_name}' Indexes...[/bold blue]")
        service.sync_indexes(dry_run=dry_run)
        console.print("[bold green]Index Sync Complete![/bold green]")
    except Exception as e:
        console.print(f"[bold red]Sync Failed:[/bold red] {e}")
        raise typer.Exit(1)
