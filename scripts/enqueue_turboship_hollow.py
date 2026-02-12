import typer
from rich.console import Console
from rich.progress import track
from pathlib import Path
import os

from cocli.core.config import get_campaign_dir
from cocli.core.queue.factory import get_queue_manager
from cocli.models.gm_item_task import GmItemTask

app = typer.Typer()
console = Console()

@app.command()
def main(
    campaign_name: str = typer.Option("turboship", "--campaign", "-c", help="Campaign name."),
    limit: int = typer.Option(0, "--limit", "-l", help="Number of prospects to enqueue. 0 for all."),
    force: bool = typer.Option(True, "--force", help="Force refresh even if data exists."),
) -> None:
    campaign_dir = get_campaign_dir(campaign_name)
    usv_input = campaign_dir / "recovery" / "hollow_place_ids.usv"

    if not usv_input.exists():
        console.print(f"[bold red]Error: USV file not found: {usv_input}[/bold red]")
        raise typer.Exit(1)

    # 1. Read from USV
    targets = []
    with open(usv_input, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\x1f")
            
            if len(parts) < 3:
                continue
                
            targets.append({
                "place_id": parts[0],
                "name": parts[1],
                "company_slug": parts[2]
            })
            
            if limit > 0 and len(targets) >= limit:
                break

    if not targets:
        console.print("[yellow]No targets found to enqueue.[/yellow]")
        return

    console.print(f"Enqueuing [bold green]{len(targets)}[/bold green] targets for re-scraping.")

    # 2. Ensure queue directory exists (Gold Standard path)
    queue_dir = campaign_dir / "queues" / "gm-details" / "pending"
    queue_dir.mkdir(parents=True, exist_ok=True)

    # 3. Get Queue Manager (Filesystem mode)
    # Using queue_type="details" maps to FilesystemGmDetailsQueue in the factory
    queue_manager = get_queue_manager("gm-details", use_cloud=False, queue_type="details", campaign_name=campaign_name)
    
    # We need to ensure the queue manager uses our Gold Standard path 'gm-details'
    # The default factory might use 'gm_list_item' or 'google_maps_details'
    # For now, let's manually override the path if needed, or trust the factory if configured correctly.
    # Looking at existing code, we might need to be explicit.
    
    enqueued_count = 0
    for target in track(targets, description="Enqueuing..."):
        task = GmItemTask(
            place_id=target["place_id"],
            campaign_name=campaign_name,
            name=target["name"],
            company_slug=target["company_slug"],
            force_refresh=force
        )
        queue_manager.push(task)
        enqueued_count += 1

    console.print(f"\n[bold green]Success![/bold green] Enqueued {enqueued_count} tasks.")

if __name__ == "__main__":
    app()
