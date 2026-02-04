import typer
from typing import Optional
from rich.console import Console
from cocli.core.config import get_campaign, get_campaign_dir
from cocli.core.queue.factory import get_queue_manager
from cocli.models.gm_item_task import GmItemTask

app = typer.Typer()
console = Console()

@app.command()
def main(campaign_name: Optional[str] = typer.Argument(None, help="Campaign name. Defaults to current context.")) -> None:
    """
    Pushes all Place IDs found in the campaign's 'inbox' directory to the Details queue.
    """
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified and no active context.[/bold red]")
        raise typer.Exit(1)

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[bold red]Error: Campaign directory not found for '{campaign_name}'.[/bold red]")
        raise typer.Exit(1)

    inbox_dir = campaign_dir / "indexes" / "google_maps_prospects" / "inbox"

    if not inbox_dir.exists():
        console.print(f"[red]Inbox directory not found: {inbox_dir}[/red]")
        return

    # Connect to Queue
    try:
        queue_manager = get_queue_manager("gm_list_item", use_cloud=True, queue_type="gm_list_item", campaign_name=campaign_name) 
    except Exception as e:
        console.print(f"[bold red]Error connecting to queue: {e}[/bold red]")
        return

    files = list(inbox_dir.glob("*.csv"))
    console.print(f"[bold]Found {len(files)} files in Inbox for campaign '{campaign_name}'. Pushing to Queue...[/bold]")
    
    count = 0
    with console.status("Pushing tasks...") as status:
        for file_path in files:
            place_id = file_path.stem
            
            task = GmItemTask(
                place_id=place_id,
                campaign_name=campaign_name,
                ack_token=None
            )
            
            queue_manager.push(task)
            count += 1
            if count % 100 == 0:
                status.update(f"Queued {count}/{len(files)}...")

    console.print(f"[bold green]Successfully queued {count} items for details scraping.[/bold green]")

if __name__ == "__main__":
    app()
