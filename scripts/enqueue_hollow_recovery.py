import typer
from rich.console import Console
from rich.progress import track
from typing import Optional
from pathlib import Path

from cocli.core.config import get_campaign_dir
from cocli.core.queue.factory import get_queue_manager
from cocli.models.gm_item_task import GmItemTask

app = typer.Typer()
console = Console()

@app.command()
def main(
    usv_input: Optional[Path] = typer.Argument(None, help="Path to input USV file. Defaults to campaigns/roadmap/recovery/hollow_place_ids.usv"),
    campaign_name: str = typer.Option("roadmap", "--campaign", "-c", help="Campaign name."),
    limit: int = typer.Option(100, "--limit", "-l", help="Number of prospects to re-scrape. Set to 0 for all."),
    force: bool = typer.Option(True, "--force", help="Force refresh even if data is recent."),
) -> None:
    """
    Reads hollow prospects from a USV and enqueues them for gm-details re-scraping.
    Preserves existing name/slug to enable the Identification Shield.
    """
    if not usv_input:
        campaign_dir = get_campaign_dir(campaign_name)
        if not campaign_dir:
            console.print(f"[bold red]Error: Could not find campaign directory for {campaign_name}[/bold red]")
            raise typer.Exit(1)
        usv_input = campaign_dir / "recovery" / "hollow_place_ids.usv"

    if not usv_input.exists():
        console.print(f"[bold red]Error: USV file not found: {usv_input}[/bold red]")
        raise typer.Exit(1)

    # 1. Read from USV (Unit Separator)
    targets = []
    with open(usv_input, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\x1f")
            
            # Extract fields with defaults if not present
            place_id = parts[0] if len(parts) > 0 else None
            name = parts[1] if len(parts) > 1 else ""
            company_slug = parts[2] if len(parts) > 2 else ""

            if not place_id:
                continue
            
            # Expected format: place_id, name, company_slug
            targets.append({
                "place_id": place_id,
                "name": name,
                "company_slug": company_slug
            })
            
            if limit > 0 and len(targets) >= limit:
                break

    if not targets:
        console.print("[yellow]No targets found in USV.[/yellow]")
        return

    console.print(f"Selected [bold green]{len(targets)}[/bold green] hollow targets from USV.")

    # 2. Enqueue
    queue_manager = get_queue_manager("gm_list_item", use_cloud=True, queue_type="gm_list_item", campaign_name=campaign_name)
    enqueued_count = 0

    for target in track(targets, description="Enqueuing tasks..."):
        # Enqueue with Identity Preservation
        task = GmItemTask(
            place_id=target["place_id"],
            campaign_name=campaign_name,
            name=target["name"],
            company_slug=target["company_slug"],
            force_refresh=force
        )
        queue_manager.push(task)
        enqueued_count += 1

    console.print("\n[bold green]Success![/bold green]")
    console.print(f"Enqueued {enqueued_count} tasks to the 'gm_list_item' queue.")

if __name__ == "__main__":
    app()
