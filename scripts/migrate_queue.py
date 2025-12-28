import typer
import json
from rich.console import Console
from rich.progress import track

from typing import Optional
from cocli.core.config import get_cocli_base_dir, get_campaign
from cocli.core.queue.factory import get_queue_manager
from cocli.models.queue import QueueMessage

app = typer.Typer()
console = Console()

@app.command()
def main(
    campaign_name: Optional[str] = typer.Argument(None, help="Campaign name. Defaults to current context."),
    delete_after: bool = typer.Option(False, "--delete", help="Delete local files after successful migration."),
) -> None:
    """
    Migrates pending messages from the Local File Queue to the Cloud SQS Queue.
    """
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified and no active context.[/bold red]")
        raise typer.Exit(1)

    # 1. Setup Local Queue Reader (Manual access to files)
    local_queue_dir = get_cocli_base_dir() / "queues" / f"{campaign_name}_enrichment" / "pending"
    if not local_queue_dir.exists():
        console.print(f"[red]Local queue directory not found: {local_queue_dir}[/red]")
        raise typer.Exit(1)

    files = list(local_queue_dir.glob("*.json"))
    console.print(f"Found {len(files)} pending messages in local queue for campaign '{campaign_name}'.")

    # 2. Setup Cloud Queue Writer
    try:
        cloud_queue = get_queue_manager("enrichment", use_cloud=True, campaign_name=campaign_name)
    except Exception as e:
        console.print(f"[bold red]Failed to connect to Cloud Queue: {e}[/bold red]")
        raise typer.Exit(1)

    # 3. Migrate
    migrated = 0
    for file_path in track(files, description="Migrating..."):
        try:
            data = json.loads(file_path.read_text())
            # Ensure clean message (remove local ack_token if any)
            if "ack_token" in data:
                del data["ack_token"]
            
            msg = QueueMessage(**data)
            
            cloud_queue.push(msg)
            migrated += 1
            
            if delete_after:
                file_path.unlink()
                
        except Exception as e:
            console.print(f"[red]Failed to migrate {file_path.name}: {e}[/red]")

    console.print(f"[bold green]Migration Complete. Moved {migrated} messages to SQS.[/bold green]")

if __name__ == "__main__":
    app()
