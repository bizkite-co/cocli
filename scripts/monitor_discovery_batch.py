# POLICY: frictionless-data-policy-enforcement
import logging
from typing import List
from rich.console import Console
from rich.table import Table

from cocli.core.paths import paths
from cocli.core.text_utils import slugify
from cocli.core.sharding import get_geo_shard, get_grid_tile_id
from cocli.models.campaigns.mission import MissionTask

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("monitor_batch")
console = Console()

def monitor_batch(campaign_name: str, batch_name: str, only_recent: bool = False) -> None:
    discovery_gen = paths.campaign(campaign_name).queue("discovery-gen")
    batch_file = discovery_gen.pending / "batches" / f"{batch_name}.usv"
    results_dir = paths.campaign(campaign_name).queue("gm-list").completed / "results"
    pending_queue_dir = paths.campaign(campaign_name).queue("gm-list").pending

    if not batch_file.exists():
        console.print(f"[red]Batch file not found: {batch_file}[/red]")
        return

    # 1. Load Batch
    tasks: List[MissionTask] = []
    with open(batch_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    tasks.append(MissionTask.from_usv(line))
                except Exception:
                    continue

    if not tasks:
        console.print("[yellow]No valid tasks found in batch.[/yellow]")
        return

    # 2. Build Status Table
    table = Table(title=f"Monitoring Batch: {batch_name} ({campaign_name})")
    table.add_column("Tile ID", style="cyan")
    table.add_column("Phrase", style="magenta")
    table.add_column("Status", justify="center")
    table.add_column("Details", style="dim")

    completed_count = 0
    in_progress_count = 0
    pending_count = 0
    legacy_count = 0

    from datetime import datetime, UTC, timedelta
    now = datetime.now(UTC)
    threshold = now - timedelta(hours=4)

    for task in tasks:
        lat_shard = get_geo_shard(float(task.latitude))
        grid_id = get_grid_tile_id(float(task.latitude), float(task.longitude))
        lat_tile, lon_tile = grid_id.split("_")
        phrase_slug = slugify(task.search_phrase)
        
        # Check for results (Completed)
        receipt_file = results_dir / lat_shard / lat_tile / lon_tile / f"{phrase_slug}.json"
        
        # Check for lease (In Progress)
        task_sub_path = f"{lat_shard}/{lat_tile}/{lon_tile}/{phrase_slug}.csv"
        lease_file = pending_queue_dir / task_sub_path / "lease.json"
        
        status = "[white]PENDING[/white]"
        details = "-"
        is_legacy = False
        
        if receipt_file.exists():
            import json
            try:
                with open(receipt_file, "r") as f:
                    data = json.load(f)
                    count = data.get("result_count", 0)
                    worker = data.get("worker_id", "unknown")
                    comp_at_str = data.get("completed_at")
                    
                    if comp_at_str:
                        comp_at = datetime.fromisoformat(comp_at_str.replace("Z", "+00:00"))
                        if comp_at > threshold:
                            status = "[bold green]DONE[/bold green]"
                            details = f"[bold]{count}[/bold] by {worker} (RECENT)"
                            completed_count += 1
                        else:
                            status = "[green]DONE[/green]"
                            details = f"{count} by {worker} (Legacy: {comp_at.strftime('%m-%d')})"
                            is_legacy = True
                            legacy_count += 1
                    else:
                        status = "[green]DONE[/green]"
                        details = f"{count} by {worker}"
                        completed_count += 1
            except Exception:
                status = "[green]DONE[/green]"
                details = "Result exists"
                completed_count += 1
        elif lease_file.exists():
            status = "[yellow]ACTIVE[/yellow]"
            try:
                import json
                with open(lease_file, "r") as f:
                    data = json.load(f)
                    worker = data.get("worker_id", "unknown")
                    details = f"Worker: {worker}"
            except Exception:
                details = "Leased"
            in_progress_count += 1
        else:
            pending_count += 1

        if not only_recent or not is_legacy:
            table.add_row(task.tile_id, task.search_phrase, status, details)

    console.print(table)
    
    # Summary
    console.print("\n[bold]Summary:[/bold]")
    console.print(f"  [bold green]Recent Done:  {completed_count}[/bold green]")
    console.print(f"  [green]Legacy Done:  {legacy_count}[/green]")
    console.print(f"  [yellow]Active:       {in_progress_count}[/yellow]")
    console.print(f"  [white]Pending:      {pending_count}[/white]")
    console.print(f"  Total:        {len(tasks)}")

if __name__ == "__main__":
    import argparse
    from cocli.core.config import get_campaign
    
    parser = argparse.ArgumentParser(description="Monitor the progress of a discovery batch.")
    parser.add_argument("batch", help="Name of the batch (without .usv)")
    parser.add_argument("--campaign", "-c", default=get_campaign(), help="Campaign name")
    parser.add_argument("--recent", action="store_true", help="Only show recent or pending tasks.")
    
    args = parser.parse_args()
    monitor_batch(args.campaign, args.batch, only_recent=args.recent)
