import os
import typer
import boto3
import json
from pathlib import Path
from datetime import datetime, timezone
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple, Optional

console = Console()
app = typer.Typer()

S3_BUCKET = "cocli-data-turboship"
DATA_DIR = Path(os.environ.get("COCLI_DATA_HOME", Path.home() / ".local/share/cocli_data"))
STATE_FILE = DATA_DIR / ".smart_sync_state.json"

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            return {}
    return {}

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state))

def download_file(s3_client, bucket: str, key: str, local_path: Path, progress, task_id) -> None:
    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        s3_client.download_file(bucket, key, str(local_path))
        progress.advance(task_id, 1)
    except Exception as e:
        console.print(f"[red]Error downloading {key}: {e}[/red]")

@app.command("companies")
def sync_companies(
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
    s3 = boto3.client("s3")
    local_base = DATA_DIR / "companies"
    prefix = "companies/"
    
    # Load State
    state = load_state()
    last_sync_ts = state.get("companies_last_sync")
    
    if last_sync_ts and not full and not force:
        last_sync_dt = datetime.fromtimestamp(last_sync_ts, tz=timezone.utc)
        console.print(f"[bold blue]Incremental Sync[/bold blue] (Newer than {last_sync_dt.strftime('%Y-%m-%d %H:%M:%S')})")
    else:
        console.print("[bold blue]Full Sync Scan[/bold blue] (Checking all files...)")

    to_download: List[Tuple[str, Path]] = []
    
    # We record the start time to save as the new 'last_sync' only if successful
    # Using a slightly buffered time (minus 1 min) to be safe against clock skew
    sync_start_time = datetime.now(timezone.utc).timestamp() - 60 

    # 1. List & Filter
    paginator = s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix)
    
    total_scanned = 0
    
    with console.status("[bold green]Scanning S3 and filtering...[/bold green]") as status:
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    total_scanned += 1
                    if total_scanned % 1000 == 0:
                        status.update(f"Scanning S3... ({total_scanned} objects found)")

                    key = obj['Key']
                    if key.endswith("/"): continue
                    
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
                    elif not full and last_sync_dt:
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
        state["companies_last_sync"] = sync_start_time
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
                    executor.submit(download_file, s3, S3_BUCKET, key, local_path, progress, task_id)
                )
            
            for f in futures:
                f.result()
                
    # Save State
    state["companies_last_sync"] = sync_start_time
    save_state(state)
    console.print("[bold green]Sync Complete![/bold green]")

if __name__ == "__main__":
    app()