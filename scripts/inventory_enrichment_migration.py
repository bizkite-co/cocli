import json
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.core.sharding import get_domain_shard

app = typer.Typer()
console = Console()

@app.command()
def inventory(
    campaign: str = typer.Argument(..., help="Campaign to scan.")
) -> None:
    """
    Scans S3 for legacy enrichment tasks and creates a migration inventory.
    """
    from cocli.services.sync_service import SyncService
    service = SyncService(campaign)
    bucket = service.bucket
    
    if not bucket:
        console.print(f"[red]Error:[/red] No bucket defined for campaign {campaign}")
        raise typer.Exit(1)
    
    legacy_prefix = f"campaigns/{campaign}/queues/enrichment/pending/"
    
    console.print(f"Scanning [bold]{bucket}/{legacy_prefix}[/bold] for legacy tasks...")
    
    # Use AWS CLI to list all task.json files in the legacy path
    cmd = [
        "aws", "s3", "ls", 
        f"s3://{bucket}/{legacy_prefix}", 
        "--recursive"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        lines = result.stdout.strip().split("\n")
        
        task_files = [line.split()[-1] for line in lines if line.endswith("task.json")]
        console.print(f"Found {len(task_files)} legacy tasks.")
        
        if not task_files:
            return

        console.print(f"Found {len(task_files)} files. Sampling first 10 for domain extraction...")
        
        # Sample extraction
        for key in task_files[:10]:
            # download content
            cat_cmd = ["aws", "s3", "cp", f"s3://{bucket}/{key}", "-"]
            task_data = json.loads(subprocess.run(cat_cmd, capture_output=True, text=True).stdout)
            domain = task_data.get("domain")
            gold_shard = get_domain_shard(domain)
            console.print(f"  {key} -> [green]{domain}[/green] (Shard: {gold_shard})")
        
        console.print(f"\n[yellow]Ready for full migration from {len(task_files)} legacy records.[/yellow]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")

if __name__ == "__main__":
    app()
