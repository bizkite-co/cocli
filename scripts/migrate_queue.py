import typer
import json
from rich.console import Console
from rich.progress import track

from cocli.core.config import get_cocli_base_dir
from cocli.core.queue.factory import get_queue_manager
from cocli.models.queue import QueueMessage

app = typer.Typer()
console = Console()

@app.command()
def main(
    campaign_name: str = typer.Argument(..., help="Campaign name."),
    delete_after: bool = typer.Option(False, "--delete", help="Delete local files after successful migration."),
) -> None:
    """
    Migrates pending messages from the Local File Queue to the Cloud SQS Queue.
    Prerequisite: The SQS Queue must be deployed and configured in env vars (COCLI_ENRICHMENT_QUEUE_URL) 
    or inferred by the factory if connected to AWS.
    """
    # 1. Setup Local Queue Reader (Manual access to files)
    local_queue_dir = get_cocli_base_dir() / "queues" / f"{campaign_name}_enrichment" / "pending"
    if not local_queue_dir.exists():
        console.print(f"[red]Local queue directory not found: {local_queue_dir}[/red]")
        raise typer.Exit(1)

    files = list(local_queue_dir.glob("*.json"))
    console.print(f"Found {len(files)} pending messages in local queue.")

    # 2. Setup Cloud Queue Writer
    # We force use_cloud=True to get SQSQueue. 
    # It requires COCLI_ENRICHMENT_QUEUE_URL env var or valid AWS setup.
    try:
        # Note: get_queue_manager might raise if env var is missing. 
        # We assume the user has set it or we can find it via CDK outputs later.
        # For now, let's assume we can instantiate SQSQueue if we know the URL.
        # BUT get_queue_manager doesn't take URL arg, it reads env.
        # So user must export COCLI_ENRICHMENT_QUEUE_URL=... before running this.
        cloud_queue = get_queue_manager(f"{campaign_name}_enrichment", use_cloud=True)
    except Exception as e:
        console.print(f"[bold red]Failed to connect to Cloud Queue: {e}[/bold red]")
        console.print("[yellow]Ensure COCLI_ENRICHMENT_QUEUE_URL environment variable is set.[/yellow]")
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
