import json
import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import track

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.core.logging_config import setup_file_logging
from cocli.models.campaigns.queue.enrichment import EnrichmentTask
from cocli.core.paths import paths

app = typer.Typer()
console = Console()
logger = logging.getLogger("migration")

@app.command()
def migrate(
    campaign: str = typer.Argument(..., help="Campaign to migrate."),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Limit number of tasks for testing."),
    dry_run: bool = typer.Option(True, " /--no-dry-run", help="Actually move data.")
) -> None:
    """
    Locally migrates legacy enrichment tasks to Gold Standard sharding.
    """
    setup_file_logging(f"migrate_local_{campaign}", disable_console=True)
    
    # Root of the pending queue
    pending_root = paths.queue(campaign, "enrichment") / "pending"
    
    if not pending_root.exists():
        console.print(f"[red]Error:[/red] Pending root {pending_root} does not exist.")
        return

    legacy_tasks = []
    # 1. Scan for Sharded Legacy Tasks (pending/{shard}/{md5}/task.json)
    for shard_dir in pending_root.iterdir():
        if shard_dir.is_dir() and len(shard_dir.name) == 1:
            for task_dir in shard_dir.iterdir():
                if task_dir.is_dir() and len(task_dir.name) == 32: 
                    task_json = task_dir / "task.json"
                    if task_json.exists():
                        legacy_tasks.append(task_json)
    
    # 2. Scan for Flat Legacy Tasks (pending/{md5}/task.json)
    for task_dir in pending_root.iterdir():
        if task_dir.is_dir() and len(task_dir.name) == 32:
            task_json = task_dir / "task.json"
            if task_json.exists():
                legacy_tasks.append(task_json)

    console.print(f"Found [bold]{len(legacy_tasks)}[/bold] legacy tasks.")
    
    if limit:
        legacy_tasks = legacy_tasks[:limit]
        console.print(f"Limiting migration to [bold]{limit}[/bold] tasks.")

    migrated_count = 0
    seen_ids = set()
    dedup_count = 0
    
    for task_path in track(legacy_tasks, description="Migrating", transient=True):
        try:
            with open(task_path, "r") as f:
                data = json.load(f)
            
            task = EnrichmentTask.model_validate({
                "domain": data["domain"],
                "company_slug": data["company_slug"],
                "campaign_name": campaign
            })
            
            if task.task_id in seen_ids:
                dedup_count += 1
                continue
            seen_ids.add(task.task_id)

            gold_dir = task.get_local_dir()
            gold_file = gold_dir / "task.json"
            
            # Details ONLY to log file
            logger.info(f"MIGRATION: {data['domain']} | {task_path.parent.name} -> {task.shard}/{task.task_id}")
            
            if not dry_run:
                gold_dir.mkdir(parents=True, exist_ok=True)
                with open(gold_file, "w") as f:
                    json.dump(task.model_dump(mode="json"), f)
                migrated_count += 1
                
        except Exception as e:
            logger.error(f"Failed to migrate {task_path}: {e}")

    console.print("\n[bold green]Migration Complete![/bold green]")
    console.print(f"Tasks Migrated (Unique): {migrated_count}")
    console.print(f"Duplicates Skipped: {dedup_count}")
    if dry_run:
        console.print("[yellow]Dry run complete. Use --no-dry-run to perform migration.[/yellow]")

if __name__ == "__main__":
    app()
