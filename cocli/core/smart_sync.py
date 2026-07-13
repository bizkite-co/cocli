import json
import logging
import sys
from pathlib import Path
from datetime import datetime, timezone
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple, Dict, Any, Optional

from .logging_config import setup_file_logging
from .config import get_cocli_base_dir

console = Console()

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
    from botocore.exceptions import ClientError
    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        s3_client.download_file(bucket, key, str(local_path))
        progress.advance(task_id, 1)
        logger.debug(f"Downloaded {key} to {local_path}")
    except ClientError as e:
        if e.response['Error']['Code'] == "404":
            # Silently ignore 404s - the file was likely moved or deleted by a worker
            progress.advance(task_id, 1)
            logger.debug(f"Skipped missing file (404): {key}")
        else:
            logger.error(f"Error downloading {key}: {e}")
            console.print(f"[red]Error downloading {key}: {e}[/red]")
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
    force: bool = False,
    completed_dir: Optional[Path] = None
) -> None:
    setup_file_logging(f"smart_sync_{target_name}")
    logger.info(f"Starting smart sync for {target_name} in campaign {campaign_name}")

    try:
        from .reporting import get_boto3_session, get_s3_client
        from botocore.config import Config
        # Prepare a config object for get_boto3_session
        config_obj = {"aws": aws_config, "campaign": {"name": campaign_name}}
        session = get_boto3_session(config_obj, max_pool_connections=workers)
        
        # MUST pass Config to the client to actually use the larger pool!
        s3_config = Config(max_pool_connections=workers)
        s3 = get_s3_client(session=session, config=s3_config)
    except Exception as e:
         logger.exception("Failed to create AWS session")
         console.print(f"[bold red]Failed to create AWS session: {e}[/bold red]")
         sys.exit(1)

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
    # If we are syncing config, don't recurse into subdirectories
    kwargs: Dict[str, Any] = {'Bucket': bucket_name, 'Prefix': prefix}
    if target_name == "campaign-config":
        kwargs['Delimiter'] = '/'
        kwargs['PaginationConfig'] = {'MaxItems': 1000}
        
    pages = paginator.paginate(**kwargs)
    
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
                            # Only download if S3 is also newer AND size changed
                            if not local_path.exists() or (s3_mtime.timestamp() > local_path.stat().st_mtime and s3_size != local_path.stat().st_size):
                                should_download = True
                            else:
                                logger.debug(f"Skipping {key}: Local file is newer or same size.")
                    else:
                        if not local_path.exists() or local_path.stat().st_size != s3_size:
                            # Even in full sync, don't overwrite newer local files unless size changed
                            if not local_path.exists() or (s3_mtime.timestamp() > local_path.stat().st_mtime and s3_size != local_path.stat().st_size):
                                should_download = True
                            else:
                                logger.debug(f"Skipping {key}: Local file is newer or same size.")
                    
                    if completed_dir:
                        # Zombie/Re-queue Check
                        parts = Path(rel_path).parts
                        if parts:
                            # V2 Key structure: <shard>/<task_id>/[task.json|lease.json]
                            # OR Legacy structure: <task_id>/[task.json|lease.json]
                            if len(parts) >= 2:
                                if len(parts[0]) == 1:
                                    # Sharded: parts[0] is shard, parts[1] is task_id
                                    task_dir_name = parts[1]
                                else:
                                    # Legacy: parts[0] is task_id
                                    task_dir_name = parts[0]
                                
                                completed_file = completed_dir / f"{task_dir_name}.json"
                                
                                if completed_file.exists():
                                    completed_mtime = completed_file.stat().st_mtime
                                    # s3_mtime is timezone-aware, convert to timestamp for comparison
                                    if s3_mtime.timestamp() > completed_mtime:
                                        logger.debug(f"Re-downloading {key}: S3 pending task is newer than local completion (Re-queue detected).")
                                        should_download = True
                                    else:
                                        # Zombie case: Completed is newer/same as pending.
                                        # 1. Don't download.
                                        should_download = False
                                        
                                        # 3. Cleanup S3 pending (The Source of the Zombie)
                                        try:
                                            logger.debug(f"Deleting Zombie S3 Object: {key}")
                                            s3.delete_object(Bucket=bucket_name, Key=key)
                                        except Exception as e:
                                            logger.error(f"Failed to delete zombie S3 key {key}: {e}")

                                        # 2. Cleanup local pending if it exists (fix the "stuck" state)
                                        if local_path.exists():
                                            try:
                                                local_path.unlink()
                                                logger.debug(f"Removed zombie local pending file: {local_path}")
                                                # Try to remove the directory if it's empty
                                                try:
                                                    local_path.parent.rmdir()
                                                    # If sharded, also try to remove the shard dir
                                                    if len(parts[0]) == 1:
                                                        local_path.parent.parent.rmdir()
                                                except OSError:
                                                    pass # Directory not empty or other error
                                            except Exception as e:
                                                logger.error(f"Failed to remove zombie file {local_path}: {e}")

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
