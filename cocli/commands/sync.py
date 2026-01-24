import os
import subprocess
import typer
from pathlib import Path
from typing import Optional, List
from rich.console import Console

console = Console()

# Define the data directory (centralized logic)
DATA_DIR = Path(os.environ.get("COCLI_DATA_HOME", Path.home() / ".local/share/data"))

def get_bucket_for_campaign(campaign_name: str) -> str:
    """Resolves the S3 bucket name for a given campaign."""
    from cocli.core.config import load_campaign_config
    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    return aws_config.get("data_bucket_name") or f"cocli-data-{campaign_name}"

def run_s3_sync(source: str, dest: str, dry_run: bool = False, exclude: List[str] = []) -> None:
    """Helper to run aws s3 sync command."""
    cmd = ["aws", "s3", "sync", source, dest]
    if dry_run:
        cmd.append("--dryrun")
        console.print(f"[dim]Dry Run Command: {' '.join(cmd)}[/dim]")
    
    for pattern in exclude:
        cmd.extend(["--exclude", pattern])

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error running sync:[/bold red] {e}")
        raise typer.Exit(code=1)

def sync(
    campaign_name: Optional[str] = typer.Argument(None, help="The campaign name to sync. Defaults to current context if not provided."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be synced without actually doing it."),
) -> None:
    """
    Bidirectional sync of indexes with S3.
    
    Syncs:
    1. Shared Scraped Areas Index (s3://.../indexes/scraped_areas/ <-> local/.../indexes/scraped_areas/)
    2. Campaign Indexes (s3://.../campaigns/{campaign}/indexes/ <-> local/.../campaigns/{campaign}/indexes/)
    
    Strategy: Merge (S3->Local, then Local->S3). No deletion of missing files.
    """
    # 1. Resolve Campaign
    if not campaign_name:
        from cocli.core.config import get_campaign
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[bold red]No campaign specified and no active campaign found. Cannot sync.[/bold red]")
        raise typer.Exit(1)

    bucket = get_bucket_for_campaign(campaign_name)
    
    # 2. Sync Shared Scraped Areas
    local_areas = DATA_DIR / "indexes" / "scraped_areas"
    s3_areas = f"s3://{bucket}/indexes/scraped_areas"
    
    if not local_areas.exists():
        console.print(f"[yellow]Local scraped_areas directory not found at {local_areas}. Creating it.[/yellow]")
        local_areas.mkdir(parents=True, exist_ok=True)

    console.print(f"[bold blue]Syncing Shared Scraped Areas using bucket: {bucket}...[/bold blue]")
    
    # Down (S3 -> Local)
    console.print("  [cyan]↓ Downloading updates from S3...[/cyan]")
    run_s3_sync(s3_areas, str(local_areas), dry_run)
    
    # Up (Local -> S3)
    console.print("  [cyan]↑ Uploading updates to S3...[/cyan]")
    run_s3_sync(str(local_areas), s3_areas, dry_run)


    # 3. Sync Campaign Indexes
    local_campaign_indexes = DATA_DIR / "campaigns" / campaign_name / "indexes"
    s3_campaign_indexes = f"s3://{bucket}/campaigns/{campaign_name}/indexes"

    if not local_campaign_indexes.exists():
         console.print(f"[yellow]Local indexes directory for campaign '{campaign_name}' not found at {local_campaign_indexes}. Creating it.[/yellow]")
         local_campaign_indexes.mkdir(parents=True, exist_ok=True)

    console.print(f"[bold blue]Syncing Campaign '{campaign_name}' Indexes...[/bold blue]")

    # Down (S3 -> Local)
    console.print("  [cyan]↓ Downloading updates from S3...[/cyan]")
    run_s3_sync(s3_campaign_indexes, str(local_campaign_indexes), dry_run)

    # Up (Local -> S3)
    console.print("  [cyan]↑ Uploading updates to S3...[/cyan]")
    run_s3_sync(str(local_campaign_indexes), s3_campaign_indexes, dry_run)

    console.print("[bold green]Sync Complete![/bold green]")
