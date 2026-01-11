import typer
import shutil
from rich.console import Console
from rich.progress import track
from typing import Optional

from cocli.core.config import get_campaign_dir, get_cocli_base_dir, get_campaign

app = typer.Typer()
console = Console()

@app.command()
def main(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c"),
    queue: str = typer.Option("enrichment", "--queue", "-q"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate migration without moving files.")
) -> None:
    """
    Migrates the Filesystem Queue from V1 (frontier/*.json) to V2 (queues/.../pending/{hash}/task.json).
    """
    if not campaign:
        campaign = get_campaign()
    
    if not campaign:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    campaign_dir = get_campaign_dir(campaign)
    if not campaign_dir:
        console.print(f"[red]Campaign directory not found for {campaign}[/red]")
        raise typer.Exit(1)

    # V1 Paths
    old_frontier = campaign_dir / "frontier" / queue
    old_leases = campaign_dir / "active-leases" / queue

    # V2 Paths
    # data/queues/<campaign>/<queue>/pending
    new_base = get_cocli_base_dir() / "data" / "queues" / campaign / queue
    new_pending = new_base / "pending"

    if not old_frontier.exists():
        console.print(f"[yellow]No V1 frontier directory found at {old_frontier}. Nothing to migrate.[/yellow]")
        return

    files = list(old_frontier.glob("*.json"))
    console.print(f"Found [bold]{len(files)}[/bold] items in V1 queue.")

    if not dry_run:
        new_pending.mkdir(parents=True, exist_ok=True)

    migrated_count = 0
    
    for task_file in track(files, description="Migrating tasks..."):
        task_id = task_file.stem
        
        # Determine V2 destination
        # Sanitize ID just in case (though MD5 usually safe)
        safe_id = task_id.replace("/", "_")
        dest_dir = new_pending / safe_id
        dest_file = dest_dir / "task.json"
        
        if dry_run:
            # console.print(f"Would move {task_file} -> {dest_file}")
            migrated_count += 1
            continue

        dest_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Move task file
            shutil.move(str(task_file), str(dest_file))
            migrated_count += 1
            
            # Check for lease
            lease_file = old_leases / f"{task_id}.lease"
            if lease_file.exists():
                dest_lease = dest_dir / "lease.json"
                shutil.move(str(lease_file), str(dest_lease))
                
        except Exception as e:
            console.print(f"[red]Error migrating {task_id}: {e}[/red]")

    console.print(f"[green]Migration complete![/green] Migrated {migrated_count} items.")
    if not dry_run:
        console.print(f"New queue location: [bold]{new_base}[/bold]")
        # Clean up empty old dirs if empty
        try:
            if not any(old_frontier.iterdir()):
                old_frontier.rmdir()
            if old_leases.exists() and not any(old_leases.iterdir()):
                old_leases.rmdir()
        except Exception:
            pass

if __name__ == "__main__":
    app()
