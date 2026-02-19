import sys
from pathlib import Path
from typing import List

import typer
from rich.console import Console

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.core.logging_config import setup_file_logging
from cocli.models.campaigns.queue.enrichment import EnrichmentTask
from cocli.core.queue.factory import get_queue_manager

app = typer.Typer()
console = Console()

@app.command()
def migrate(
    campaign: str = typer.Argument(..., help="Campaign to migrate."),
    domains: List[str] = typer.Argument(..., help="Specific domains to migrate."),
    dry_run: bool = typer.Option(True, "--no-dry-run", is_flag=False, help="Actually move data.")
) -> None:
    """
    Migrates specific domains from legacy MD5 sharding to Gold Standard sharding.
    """
    from cocli.services.sync_service import SyncService
    setup_file_logging(f"migrate_specific_{campaign}")
    
    service = SyncService(campaign)
    bucket = service.bucket
    
    if not bucket:
        console.print(f"[red]Error:[/red] No bucket defined for campaign {campaign}")
        raise typer.Exit(1)
    
    # We use the NEW queue manager to push
    queue = get_queue_manager("enrichment", queue_type="enrichment", campaign_name=campaign, use_cloud=True)
    
    for domain in domains:
        console.print(f"Migrating [bold]{domain}[/bold]...")
        
        # 1. Create the Gold Standard Task
        task = EnrichmentTask.model_validate({
            "domain": domain,
            "company_slug": "migration-source", # Slug is secondary now
            "campaign_name": campaign
        })
        
        shard = task.shard
        gold_id = task.task_id
        
        console.print(f"  Target Shard: {shard}")
        console.print(f"  Target ID: {gold_id}")
        
        if not dry_run:
            queue.push(task)
            console.print("  [green]✅ Migrated to S3[/green]")
        else:
            console.print(f"  [yellow](Dry Run) Would push to s3://{bucket}/{str(task.get_s3_task_key())}[/yellow]")

if __name__ == "__main__":
    app()
