import typer
import boto3
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple, Dict, Any, Optional

from ..core.logging_config import setup_file_logging
from ..core.config import get_cocli_base_dir

console = Console()
app = typer.Typer()

DATA_DIR = get_cocli_base_dir()
STATE_FILE = DATA_DIR / ".smart_sync_state.json"

logger = logging.getLogger(__name__)

def load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text()) # type: ignore
        except Exception as e:
            logger.error(f"Failed to load state file: {e}")
            return {}
    return {}

def save_state(state: Dict[str, Any]) -> None:
    try:
        STATE_FILE.write_text(json.dumps(state))
    except Exception as e:
        logger.error(f"Failed to save state file: {e}")

def download_file(s3_client: Any, bucket: str, key: str, local_path: Path, progress: Any, task_id: Any) -> None:
    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        s3_client.download_file(bucket, key, str(local_path))
        progress.advance(task_id, 1)
        logger.debug(f"Downloaded {key} to {local_path}")
    except Exception as e:
        logger.error(f"Error downloading {key}: {e}")
        console.print(f"[red]Error downloading {key}: {e}[/red]")

def run_smart_sync(
    target_name: str,
    bucket_name: str,
    prefix: str,
    local_base: Path,
    campaign_name: str,
    aws_config: Dict[str, Any],
    workers: int = 20,
    full: bool = False,
    force: bool = False
) -> None:
    setup_file_logging(f"smart_sync_{target_name}")
    logger.info(f"Starting smart sync for {target_name} in campaign {campaign_name}")

    profile_name = aws_config.get("profile") or aws_config.get("aws_profile")
    
    try:
        if profile_name:
            logger.info(f"Using AWS profile: {profile_name}")
            session = boto3.Session(profile_name=profile_name)
        else:
            session = boto3.Session()
        s3 = session.client("s3")
    except Exception as e:
         logger.exception("Failed to create AWS session")
         console.print(f"[bold red]Failed to create AWS session: {e}[/bold red]")
         raise typer.Exit(code=1)

    # Load State
    state = load_state()
    state_key = f"{campaign_name}_{target_name}_last_sync"
    last_sync_ts = state.get(state_key)
    
    if last_sync_ts and not full and not force:
        last_sync_dt = datetime.fromtimestamp(last_sync_ts, tz=timezone.utc)
        console.print(f"[bold blue]Incremental Sync for {target_name}[/bold blue] (Newer than {last_sync_dt.strftime('%Y-%m-%d %H:%M:%S')})")
        logger.info(f"Incremental sync. Last sync: {last_sync_dt}")
    else:
        last_sync_dt = None
        console.print(f"[bold blue]Full Sync Scan for {target_name}[/bold blue] (Checking all files...)")
        logger.info("Full sync scan.")

    to_download: List[Tuple[str, Path]] = []
    sync_start_time = datetime.now(timezone.utc).timestamp() - 60 

    # 1. List & Filter
    paginator = s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)
    
    total_scanned = 0
    
    with console.status(f"[bold green]Scanning s3://{bucket_name}/{prefix}...[/bold green]") as status:
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    total_scanned += 1
                    if total_scanned % 500 == 0:
                        status.update(f"[bold green]Scanning S3... ({total_scanned} objects found)[/bold green]")

                    key = obj['Key']
                    if key.endswith("/"):
                        continue
                    
                    s3_mtime = obj['LastModified'] 
                    s3_size = obj['Size']

                    # Determine local path
                    rel_path = key[len(prefix):] if key.startswith(prefix) else key
                    local_path = local_base / rel_path

                    should_download = False
                    if force:
                        should_download = True
                    elif last_sync_dt:
                        if s3_mtime > last_sync_dt:
                            # Only download if S3 is also newer than the actual local file
                            if not local_path.exists() or s3_mtime.timestamp() > local_path.stat().st_mtime:
                                should_download = True
                            else:
                                logger.info(f"Skipping {key}: Local file is newer than S3 version.")
                    else:
                        if not local_path.exists() or local_path.stat().st_size != s3_size:
                            # Even in full sync, don't overwrite newer local files unless forced
                            if not local_path.exists() or s3_mtime.timestamp() > local_path.stat().st_mtime:
                                should_download = True
                            else:
                                logger.info(f"Skipping {key}: Local file is newer than S3 version (full scan).")
                    
                    if should_download:
                        to_download.append((key, local_path))
    
    console.print(f"Scanned {total_scanned} objects. Found {len(to_download)} updates.")
    logger.info(f"Scanned {total_scanned} objects. {len(to_download)} to download.")

    if not to_download:
        console.print(f"[green]{target_name} is up to date.[/green]")
        state[state_key] = sync_start_time
        save_state(state)
        return
    
    # 2. Download
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task(f"Downloading {target_name}...", total=len(to_download))
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(download_file, s3, bucket_name, key, local_path, progress, task_id) for key, local_path in to_download]
            for f in futures:
                try:
                    f.result()
                except Exception as e:
                    logger.error(f"Future result error: {e}")
                
    # Save State
    state[state_key] = sync_start_time
    save_state(state)
    console.print(f"[bold green]{target_name} Sync Complete![/bold green]")
    logger.info(f"{target_name} sync complete.")

@app.command("companies")
def sync_companies(
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name"),
    workers: int = typer.Option(20, help="Number of concurrent download threads."),
    full: bool = typer.Option(False, "--full", help="Perform a full integrity check (slower)."),
    force: bool = typer.Option(False, "--force", help="Force download all files."),
) -> None:
    from ..core.config import get_campaign, load_campaign_config
    campaign_name = campaign_name or get_campaign()
    if not campaign_name:
        console.print("[bold red]No campaign specified.[/bold red]")
        raise typer.Exit(1)
    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    bucket_name = aws_config.get("cocli_data_bucket_name") or f"cocli-data-{campaign_name}"
    run_smart_sync("companies", bucket_name, "companies/", DATA_DIR / "companies", campaign_name, aws_config, workers, full, force)

@app.command("prospects")
def sync_prospects(
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name"),
    workers: int = typer.Option(20, help="Number of concurrent download threads."),
    full: bool = typer.Option(False, "--full", help="Perform a full integrity check (slower)."),
    force: bool = typer.Option(False, "--force", help="Force download all files."),
) -> None:
    from ..core.config import get_campaign, load_campaign_config
    campaign_name = campaign_name or get_campaign()
    if not campaign_name:
        console.print("[bold red]No campaign specified.[/bold red]")
        raise typer.Exit(1)
    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    bucket_name = aws_config.get("cocli_data_bucket_name") or f"cocli-data-{campaign_name}"
    prefix = f"campaigns/{campaign_name}/indexes/google_maps_prospects/"
    local_base = DATA_DIR / "campaigns" / campaign_name / "indexes" / "google_maps_prospects"
    run_smart_sync("prospects", bucket_name, prefix, local_base, campaign_name, aws_config, workers, full, force)

@app.command("emails")
def sync_emails(
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name"),
    workers: int = typer.Option(20, help="Number of concurrent download threads."),
    full: bool = typer.Option(False, "--full", help="Perform a full integrity check (slower)."),
    force: bool = typer.Option(False, "--force", help="Force download all files."),
) -> None:
    from ..core.config import get_campaign, load_campaign_config
    campaign_name = campaign_name or get_campaign()
    if not campaign_name:
        console.print("[bold red]No campaign specified.[/bold red]")
        raise typer.Exit(1)
    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    bucket_name = aws_config.get("cocli_data_bucket_name") or f"cocli-data-{campaign_name}"
    prefix = f"campaigns/{campaign_name}/indexes/emails/"
    local_base = DATA_DIR / "campaigns" / campaign_name / "indexes" / "emails"
    run_smart_sync("emails", bucket_name, prefix, local_base, campaign_name, aws_config, workers, full, force)

@app.command("scraped-areas")
def sync_scraped_areas(
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name"),
    workers: int = typer.Option(20, help="Number of concurrent download threads."),
    full: bool = typer.Option(False, "--full", help="Perform a full integrity check (slower)."),
    force: bool = typer.Option(False, "--force", help="Force download all files."),
) -> None:
    from ..core.config import get_campaign, load_campaign_config
    campaign_name = campaign_name or get_campaign()
    if not campaign_name:
        console.print("[bold red]No campaign specified.[/bold red]")
        raise typer.Exit(1)
    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    bucket_name = aws_config.get("cocli_data_bucket_name") or f"cocli-data-{campaign_name}"
    run_smart_sync("scraped-areas", bucket_name, "indexes/scraped_areas/", DATA_DIR / "indexes" / "scraped_areas", campaign_name, aws_config, workers, full, force)

@app.command("scraped-tiles")
def sync_scraped_tiles(
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name"),
    workers: int = typer.Option(20, help="Number of concurrent download threads."),
    full: bool = typer.Option(False, "--full", help="Perform a full integrity check (slower)."),
    force: bool = typer.Option(False, "--force", help="Force download all files."),
) -> None:
    from ..core.config import get_campaign, load_campaign_config
    campaign_name = campaign_name or get_campaign()
    if not campaign_name:
        console.print("[bold red]No campaign specified.[/bold red]")
        raise typer.Exit(1)
    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    bucket_name = aws_config.get("cocli_data_bucket_name") or f"cocli-data-{campaign_name}"
    run_smart_sync("scraped-tiles", bucket_name, "indexes/scraped-tiles/", DATA_DIR / "indexes" / "scraped-tiles", campaign_name, aws_config, workers, full, force)

@app.command("enrichment-queue")
def sync_enrichment_queue(
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name"),
    workers: int = typer.Option(20, help="Number of concurrent download threads."),
    full: bool = typer.Option(False, "--full", help="Perform a full integrity check (slower)."),
    force: bool = typer.Option(False, "--force", help="Force download all files."),
) -> None:
    from ..core.config import get_campaign, load_campaign_config
    campaign_name = campaign_name or get_campaign()
    if not campaign_name:
        console.print("[bold red]No campaign specified.[/bold red]")
        raise typer.Exit(1)
    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    bucket_name = aws_config.get("cocli_data_bucket_name") or f"cocli-data-{campaign_name}"
    prefix = f"campaigns/{campaign_name}/frontier/enrichment/"
    local_base = DATA_DIR / "campaigns" / campaign_name / "frontier" / "enrichment"
    run_smart_sync("enrichment-queue", bucket_name, prefix, local_base, campaign_name, aws_config, workers, full, force)

@app.command("campaign-config")
def sync_campaign_config(
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name"),
) -> None:
    from ..core.config import get_campaign
    campaign_name = campaign_name or get_campaign()
    if not campaign_name:
        console.print("[bold red]No campaign specified.[/bold red]")
        raise typer.Exit(1)
    
    # We can't use load_campaign_config if the file doesn't exist yet!
    # But we can assume the bucket name pattern.
    bucket_name = f"cocli-data-{campaign_name}"
    prefix = f"campaigns/{campaign_name}/"
    local_base = DATA_DIR / "campaigns" / campaign_name
    
    # Since run_smart_sync needs aws_config, and we might not have it yet, 
    # we'll try to use a default session.
    run_smart_sync("campaign-config", bucket_name, prefix, local_base, campaign_name, {}, workers=1)

if __name__ == "__main__":
    app()