import os
import typer
import boto3
import json
from pathlib import Path
from datetime import datetime, timezone
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple, Dict, Any, Optional

console = Console()
app = typer.Typer()

S3_BUCKET = "cocli-data-turboship"
DATA_DIR = Path(os.environ.get("COCLI_DATA_HOME", Path.home() / ".local/share/cocli_data"))
STATE_FILE = DATA_DIR / ".smart_sync_state.json"

def load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text()) # type: ignore
        except Exception:
            return {}
    return {}

def save_state(state: Dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state))

def download_file(s3_client: Any, bucket: str, key: str, local_path: Path, progress: Any, task_id: Any) -> None:
    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        s3_client.download_file(bucket, key, str(local_path))
        progress.advance(task_id, 1)
    except Exception as e:
        console.print(f"[red]Error downloading {key}: {e}[/red]")

@app.command("companies")
def sync_companies(
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name"),
    workers: int = typer.Option(20, help="Number of concurrent download threads."),
    full: bool = typer.Option(False, "--full", help="Perform a full integrity check (slower). Checks file sizes/existence locally."),
    force: bool = typer.Option(False, "--force", help="Force download all files (overwrites local)."),
) -> None:
    """
    Smartly syncs the 'companies' directory from S3 to local.
    
    Default behavior: INCREMENTAL.
    Only checks files modified in S3 since the last successful sync.
    
    Use --full to scan all files and check for missing/changed files locally.
    """
    from ..core.config import get_campaign, load_campaign_config
    
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[bold red]No campaign specified or active context.[/bold red]")
        raise typer.Exit(code=1)
             
    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    profile_name = aws_config.get("profile") or aws_config.get("aws_profile")
    
    # Bucket convention
    bucket_name = f"cocli-data-{campaign_name}"
    
    try:
        if profile_name:
            session = boto3.Session(profile_name=profile_name)
        else:
            session = boto3.Session()
        s3 = session.client("s3")
    except Exception as e:
         console.print(f"[bold red]Failed to create AWS session: {e}[/bold red]")
         raise typer.Exit(code=1)

    local_base = DATA_DIR / "companies" # Note: This might need to be campaign-specific too? 
    # Convention seems to be all companies in one shared folder, OR campaign specific?
    # Context says "companies are stored in folders slugified from their Name...". 
    # If the bucket is campaign-specific, do we mix them locally?
    # For now, keeping DATA_DIR/companies as is, assuming it's a shared local store or correct.
    
    prefix = "companies/"
    
    # Load State
    state = load_state()
    last_sync_ts = state.get(f"{campaign_name}_companies_last_sync")
    
    if last_sync_ts and not full and not force:
        last_sync_dt = datetime.fromtimestamp(last_sync_ts, tz=timezone.utc)
        console.print(f"[bold blue]Incremental Sync for {campaign_name}[/bold blue] (Newer than {last_sync_dt.strftime('%Y-%m-%d %H:%M:%S')})")
    else:
        console.print(f"[bold blue]Full Sync Scan for {campaign_name}[/bold blue] (Checking all files...)")

    to_download: List[Tuple[str, Path]] = []
    
    # We record the start time to save as the new 'last_sync' only if successful
    # Using a slightly buffered time (minus 1 min) to be safe against clock skew
    sync_start_time = datetime.now(timezone.utc).timestamp() - 60 

    # 1. List & Filter
    paginator = s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)
    
    total_scanned = 0
    
    with console.status(f"[bold green]Scanning s3://{bucket_name} and filtering...[/bold green]") as status:
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    total_scanned += 1
                    if total_scanned % 1000 == 0:
                        status.update(f"Scanning S3... ({total_scanned} objects found)")

                    key = obj['Key']
                    if key.endswith("/"):
                        continue
                    
                    s3_mtime = obj['LastModified'] # datetime with timezone
                    s3_size = obj['Size']

                    # Determine local path
                    if key.startswith(prefix):
                        rel_path = key[len(prefix):]
                    else:
                        rel_path = key
                    local_path = local_base / rel_path

                    should_download = False

                    if force:
                        should_download = True
                    elif not full and last_sync_ts: # Check last_sync_ts/dt existence
                        # Incremental Mode: Only check time
                        if s3_mtime > last_sync_dt:
                            should_download = True
                    else:
                        # Full Mode: Check existence and size
                        if not local_path.exists():
                            should_download = True
                        elif local_path.stat().st_size != s3_size:
                            should_download = True
                    
                    if should_download:
                        to_download.append((key, local_path))
    
    console.print(f"Scanned {total_scanned} objects. Found {len(to_download)} updates.")

    if not to_download:
        console.print("[green]Up to date.[/green]")
        # Update timestamp even if nothing downloaded, to mark we checked up to this point
        state[f"{campaign_name}_companies_last_sync"] = sync_start_time
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
    ) as progress:
        task_id = progress.add_task("Downloading...", total=len(to_download))
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = []
            for key, local_path in to_download:
                futures.append(
                    executor.submit(download_file, s3, bucket_name, key, local_path, progress, task_id)
                )
            
            for f in futures:
                f.result()
                
    # Save State
    state[f"{campaign_name}_companies_last_sync"] = sync_start_time
    save_state(state)
    console.print("[bold green]Sync Complete![/bold green]")

if __name__ == "__main__":
    app()