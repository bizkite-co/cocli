import typer
import logging
import json
from pathlib import Path
from datetime import datetime
from rich.console import Console

console = Console()
logger = logging.getLogger(__name__)

app = typer.Typer(help="Commands for managing sharded indexes.")

def setup_index_logging(campaign_name: str, index_name: str) -> Path:
    logs_dir = Path(".logs")
    logs_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"compact_{campaign_name}_{index_name}_{timestamp}.log"
    
    # Configure root logger to write to file
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_file)],
        force=True
    )
    # Silence third-party loggers to terminal
    for name in ["botocore", "boto3", "urllib3", "duckdb"]:
        logging.getLogger(name).setLevel(logging.WARNING)
        
    return log_file

@app.command(name="compact")
def compact(
    campaign: str = typer.Option("roadmap", help="Campaign name"),
    index: str = typer.Option("google_maps_prospects", help="Index name to compact"),
    debug: bool = typer.Option(False, help="Enable debug logging")
) -> None:
    """
    Compact the Write-Ahead Log (WAL) into the main Checkpoint.
    Uses S3-Native isolation to prevent race conditions.
    """
    log_file = setup_index_logging(campaign, index)
    
    if debug:
        logging.getLogger("cocli").setLevel(logging.DEBUG)
        
    from ..core.compact import CompactManager
    from rich.progress import Progress, SpinnerColumn, TextColumn
    
    console.print(f"Compacting index [bold]{index}[/bold] for [bold]{campaign}[/bold]")
    console.print(f"Detailed logs: [cyan]{log_file}[/cyan]")
    
    manager = CompactManager(campaign_name=campaign, index_name=index, log_file=log_file)
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            
            # 0. Check for Interrupted Runs (Self-Healing)
            task_heal = progress.add_task("Checking for interrupted runs...", total=None)
            # Find any folders in 'processing/' on S3
            paginator = manager.s3.get_paginator('list_objects_v2')
            proc_prefix = manager.s3_index_prefix + "processing/"
            pages = paginator.paginate(Bucket=manager._bucket, Prefix=proc_prefix, Delimiter='/')
            
            interrupted_runs = []
            for page in pages:
                if 'CommonPrefixes' in page:
                    for cp in page['CommonPrefixes']:
                        # Extract the run_id from the prefix
                        interrupted_run_id = cp['Prefix'].split('/')[-2]
                        interrupted_runs.append(interrupted_run_id)
            
            if interrupted_runs:
                progress.update(task_heal, description=f"[yellow]Found {len(interrupted_runs)} interrupted runs. Recovering...")
                for run_id in interrupted_runs:
                    logger.info(f"Recovering interrupted run: {run_id}")
                    # Point manager to this specific run
                    manager.run_id = run_id
                    manager.s3_proc_prefix = manager.s3_index_prefix + f"processing/{run_id}/"
                    manager.local_proc_dir = manager.index_dir / "processing" / run_id
                    
                    # Complete the ingestion
                    manager.acquire_staging()
                    manager.merge()
                    manager.commit_remote()
                    manager.cleanup()
                progress.update(task_heal, description="[green]Recovery complete.")
            else:
                progress.update(task_heal, description="[green]No interrupted runs found.")

            # 1. Lock
            task_lock = progress.add_task("Acquiring S3 lock...", total=None)
            if not manager.acquire_lock():
                progress.update(task_lock, description="[red]Lock acquisition failed (check logs).")
                raise typer.Exit(1)
            progress.update(task_lock, description="[green]Lock acquired.")
            
            try:
                # 2. Isolate
                task_iso = progress.add_task("Isolating WAL files on S3...", total=None)
                moved = manager.isolate_wal()
                if moved == 0:
                    progress.update(task_iso, description="[yellow]Nothing to compact.")
                    return
                progress.update(task_iso, description=f"[green]Isolated {moved} files.")
                
                # 3. Ingest
                task_ingest = progress.add_task("Downloading staging data...", total=None)
                manager.acquire_staging()
                progress.update(task_ingest, description="[green]Staging data acquired.")
                
                # 4. Merge
                task_merge = progress.add_task("Merging checkpoint (DuckDB)...", total=None)
                manager.merge()
                progress.update(task_merge, description="[green]Merge complete.")
                
                # 5. Commit
                task_commit = progress.add_task("Uploading new checkpoint to S3...", total=None)
                manager.commit_remote()
                progress.update(task_commit, description="[green]S3 Checkpoint updated.")
                
                # 6. Cleanup
                task_clean = progress.add_task("Cleaning up...", total=None)
                manager.cleanup()
                progress.update(task_clean, description="[green]Cleanup complete.")
                
            finally:
                manager.release_lock()
                
        console.print("[bold green]Compaction workflow finished successfully.[/bold green]")
        
    except Exception as e:
        console.print(f"[bold red]Compaction failed: {e}[/bold red]")
        logging.error(f"Compaction failed: {e}", exc_info=True)
        raise typer.Exit(code=1)

@app.command(name="status")
def status(
    campaign: str = typer.Option("roadmap", help="Campaign name"),
    index: str = typer.Option("google_maps_prospects", help="Index name")
) -> None:
    """
    Show the status of the index tiers (WAL, Processing, Checkpoint).
    """
    from ..core.compact import CompactManager
    manager = CompactManager(campaign_name=campaign, index_name=index)
    
    console.print(f"Status for index [bold]{index}[/bold] in campaign [bold]{campaign}[/bold]:")
    
    # 1. Check for Lock
    try:
        lock_obj = manager.s3.get_object(Bucket=manager._bucket, Key=manager.s3_lock_key)
        lock_data = json.loads(lock_obj['Body'].read().decode('utf-8'))
        console.print(f"[bold yellow]LOCK ACTIVE[/bold yellow]: Run ID {lock_data.get('run_id')} started at {lock_data.get('created_at')} on {lock_data.get('host')}")
    except manager.s3.exceptions.NoSuchKey:
        console.print("Lock: [green]Available[/green]")
    except Exception as e:
        console.print(f"Lock: [red]Error checking lock: {e}[/red]")

    # 2. Count WAL Backlog
    wal_count = 0
    paginator = manager.s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=manager._bucket, Prefix=manager.s3_wal_prefix)
    for page in pages:
        if 'Contents' in page:
            wal_count += len([obj for obj in page['Contents'] if obj['Key'].endswith(('.usv', '.csv'))])
    
    console.print(f"WAL Backlog (Hot): [bold cyan]{wal_count}[/bold cyan] files waiting for checkpointing.")

    # 3. Check Processing (Staging)
    proc_prefix = manager.s3_index_prefix + "processing/"
    proc_pages = paginator.paginate(Bucket=manager._bucket, Prefix=proc_prefix)
    proc_count = 0
    for page in proc_pages:
        if 'Contents' in page:
            proc_count += len(page['Contents'])
    
    if proc_count > 0:
        console.print(f"Processing (Staging): [bold yellow]{proc_count}[/bold yellow] files currently isolated.")
    else:
        console.print("Processing: [green]Empty[/green]")

    # 4. Checkpoint State
    checkpoint_key = manager.s3_index_prefix + "prospects.checkpoint.usv"
    try:
        head = manager.s3.head_object(Bucket=manager._bucket, Key=checkpoint_key)
        size_mb = head['ContentLength'] / 1024 / 1024
        last_modified = head['LastModified'].strftime("%Y-%m-%d %H:%M:%S")
        console.print(f"Checkpoint (Cold): [bold blue]{size_mb:.2f} MB[/bold blue] (Last updated: {last_modified})")
    except manager.s3.exceptions.NoSuchKey:
        console.print("Checkpoint: [red]Not found[/red]")
    except Exception as e:
        console.print(f"Checkpoint: [red]Error: {e}[/red]")

@app.command(name="backfill-domains")
def backfill_domains(
    campaign: str = typer.Option("roadmap", help="Campaign name"),
    limit: int = typer.Option(0, "--limit", "-l", help="Limit the number of companies processed (for testing)."),
    compact: bool = typer.Option(True, "--compact/--no-compact", help="Automatically run compaction after backfill.")
) -> None:
    """
    Backfill the Domain Index from local website enrichment files.
    """
    from ..core.domain_index_manager import DomainIndexManager
    from ..models.campaigns.campaign import Campaign as CampaignModel
    from ..core.config import load_campaign_config
    from rich.progress import Progress, SpinnerColumn, TextColumn
    
    console.print(f"Backfilling Domain Index for campaign: [bold]{campaign}[/bold]")
    
    # Load campaign to get the tag
    try:
        camp_obj = CampaignModel.load(campaign)
        config = load_campaign_config(campaign)
        tag = config.get("campaign", {}).get("tag") or campaign
    except Exception as e:
        console.print(f"[bold red]Error loading campaign:[/bold red] {e}")
        raise typer.Exit(1)

    manager = DomainIndexManager(camp_obj)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task(f"Scanning companies for tag '{tag}'...", total=None)
        added = manager.backfill_from_companies(tag, limit=limit)
        progress.update(task, description=f"[green]Scanned and added {added} records to inbox.")
        
        if compact and added > 0:
            task_compact = progress.add_task("Compacting inbox into shards...", total=None)
            manager.compact_inbox()
            progress.update(task_compact, description="[green]Compaction complete.")

    console.print(f"[bold green]Success![/bold green] Backfill process finished for [cyan]{campaign}[/cyan].")

@app.command(name="write-datapackage")
def write_datapackage(
    campaign: str = typer.Option("roadmap", help="Campaign name"),
    index_model: str = typer.Option("google_maps_prospects", help="Index model to use (google_maps_prospects, domains)")
) -> None:
    """
    Generates Frictionless Data 'datapackage.json' for the specified index.
    """
    from typing import Type, Union
    model_cls: Union[Type['GoogleMapsProspect'], Type['WebsiteDomainCsv']]

    if index_model == "google_maps_prospects":
        from ..models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
        model_cls = GoogleMapsProspect
    elif index_model == "domains":
        from ..models.campaigns.indexes.domains import WebsiteDomainCsv
        model_cls = WebsiteDomainCsv
    else:
        console.print(f"[bold red]Unknown index model: {index_model}[/bold red]")
        raise typer.Exit(code=1)

    try:
        path = model_cls.write_datapackage(campaign)
        console.print(f"[bold green]Successfully wrote datapackage.json to: {path}[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Failed to write datapackage: {e}[/bold red]")
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
