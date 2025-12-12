import os
import subprocess
import typer
from pathlib import Path
from rich.console import Console

console = Console()

# Define the data directory (centralized logic)
DATA_DIR = Path(os.environ.get("COCLI_DATA_HOME", Path.home() / ".local/share/cocli_data"))
S3_BUCKET = "cocli-data-turboship"

def run_s3_sync(source: str, dest: str, dry_run: bool = False, exclude: list[str] = []) -> None:
    """Helper to run aws s3 sync command."""
    cmd = ["aws", "s3", "sync", source, dest]
    if dry_run:
        cmd.append("--dryrun")
        console.print(f"[dim]Dry Run Command: {' '.join(cmd)}[/dim]")
    
    for pattern in exclude:
        cmd.extend(["--exclude", pattern])

    # console.print(f"[dim]Running: {' '.join(cmd)}[/dim]") # too verbose
    
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error running sync:[/bold red] {e}")
        raise typer.Exit(code=1)

def sync(
    campaign_name: str = typer.Argument(None, help="The campaign name to sync. Defaults to current context if not provided."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be synced without actually doing it."),
) -> None:
    """
    Bidirectional sync of indexes with S3.
    
    Syncs:
    1. Shared Scraped Areas Index (s3://.../indexes/scraped_areas/ <-> local/.../indexes/scraped_areas/)
    2. Campaign Indexes (s3://.../campaigns/{campaign}/indexes/ <-> local/.../campaigns/{campaign}/indexes/)
    
    Strategy: Merge (S3->Local, then Local->S3). No deletion of missing files (to avoid deleting new files created on other side).
    """
    
    # 1. Sync Shared Scraped Areas
    local_areas = DATA_DIR / "indexes" / "scraped_areas"
    s3_areas = f"s3://{S3_BUCKET}/indexes/scraped_areas"
    
    if not local_areas.exists():
        console.print(f"[yellow]Local scraped_areas directory not found at {local_areas}. Creating it.[/yellow]")
        local_areas.mkdir(parents=True, exist_ok=True)

    console.print("[bold blue]Syncing Shared Scraped Areas...[/bold blue]")
    
    # Down (S3 -> Local)
    console.print("  [cyan]↓ Downloading updates from S3...[/cyan]")
    run_s3_sync(s3_areas, str(local_areas), dry_run)
    
    # Up (Local -> S3)
    console.print("  [cyan]↑ Uploading updates to S3...[/cyan]")
    run_s3_sync(str(local_areas), s3_areas, dry_run)


    # 2. Sync Campaign Indexes
    if not campaign_name:
        # Try to load context
        context_file = DATA_DIR / "context.txt"
        if context_file.exists():
            campaign_name = context_file.read_text().strip()
    
    if not campaign_name:
        console.print("[yellow]No campaign specified and no current context found. Skipping campaign sync.[/yellow]")
        return

    local_campaign_indexes = DATA_DIR / "campaigns" / campaign_name / "indexes"
    s3_campaign_indexes = f"s3://{S3_BUCKET}/campaigns/{campaign_name}/indexes"

    if not local_campaign_indexes.exists():
         console.print(f"[yellow]Local indexes directory for campaign '{campaign_name}' not found at {local_campaign_indexes}. Skipping campaign sync.[/yellow]")
         return

    console.print(f"[bold blue]Syncing Campaign '{campaign_name}' Indexes...[/bold blue]")

    # Down (S3 -> Local)
    console.print("  [cyan]↓ Downloading updates from S3...[/cyan]")
    run_s3_sync(s3_campaign_indexes, str(local_campaign_indexes), dry_run)

    # Up (Local -> S3)
    console.print("  [cyan]↑ Uploading updates to S3...[/cyan]")
    run_s3_sync(str(local_campaign_indexes), s3_campaign_indexes, dry_run)

    console.print("[bold green]Sync Complete![/bold green]")