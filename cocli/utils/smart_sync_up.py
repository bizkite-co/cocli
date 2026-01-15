import boto3
import json
import logging
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional

from ..core.config import get_cocli_base_dir

logger = logging.getLogger(__name__)

def get_state_file() -> Path:
    return get_cocli_base_dir() / ".smart_sync_up_state.json"

def load_state() -> Dict[str, Any]:
    state_file = get_state_file()
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text())
            if isinstance(data, dict):
                return data
        except Exception as e:
            logger.error(f"Failed to load state file: {e}")
    return {}

def save_state(state: Dict[str, Any]) -> None:
    try:
        get_state_file().write_text(json.dumps(state))
    except Exception as e:
        logger.error(f"Failed to save state file: {e}")

def upload_file(s3_client: Any, bucket: str, local_path: Path, key: str) -> None:
    try:
        s3_client.upload_file(str(local_path), bucket, key)
        logger.debug(f"Uploaded {local_path} to {key}")
    except Exception as e:
        logger.error(f"Error uploading {local_path}: {e}")

def run_smart_sync_up(
    target_name: str,
    bucket_name: str,
    prefix: str,
    local_base: Path,
    campaign_name: str,
    aws_config: Dict[str, Any],
    workers: int = 20,
    delete_remote: bool = False,
    only_modified_since_minutes: Optional[int] = None
) -> None:
    logger.info(f"Starting smart sync UP for {target_name} to s3://{bucket_name}/{prefix}")
    
    # Load state
    state = load_state()
    state_key = f"{campaign_name}_{target_name}_last_sync_up"
    last_sync_ts = state.get(state_key)
    
    sync_start_time = time.time()
    
    profile_name = aws_config.get("profile") or aws_config.get("aws_profile")
    
    try:
        from botocore.config import Config
        if profile_name:
            session = boto3.Session(profile_name=profile_name)
        else:
            session = boto3.Session()
        # Increase pool size to match or exceed the number of workers
        config = Config(max_pool_connections=50)
        s3 = session.client("s3", config=config)
    except Exception as e:
         logger.error(f"Failed to create AWS session for upload: {e}")
         return

    # 1. List Local Files
    local_files: Dict[str, Path] = {}
    if local_base.exists():
        logger.info(f"Scanning local directory: {local_base}")
        
        # Use state-based cutoff OR explicit minutes cutoff
        cutoff = None
        if only_modified_since_minutes:
            cutoff = (datetime.now(timezone.utc) - timedelta(minutes=only_modified_since_minutes)).timestamp()
        elif last_sync_ts:
            # Use state with a 10-second overlap to ensure no gaps from disk latency
            cutoff = last_sync_ts - 10
            
        if cutoff:
            cutoff_dt = datetime.fromtimestamp(cutoff, tz=timezone.utc)
            logger.info(f"Filtering for files modified since {cutoff_dt.isoformat()}")

        for path in local_base.rglob("*"):
            if path.is_file():
                if cutoff and path.stat().st_mtime < cutoff:
                    continue
                try:
                    rel_path = str(path.relative_to(local_base))
                    local_files[rel_path] = path
                except Exception:
                    continue
    else:
        logger.warning(f"Local base directory does not exist: {local_base}")

    # 2. List Remote Files (Only if we need to delete or check for existing files)
    remote_keys: Dict[str, str] = {}
    if delete_remote:
        logger.info(f"Scanning S3 prefix for deletions: s3://{bucket_name}/{prefix}")
        paginator = s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    key = str(obj['Key'])
                    rel_path = key[len(prefix):] if key.startswith(prefix) else key
                    remote_keys[rel_path] = key
    else:
        logger.info("Skipping S3 scan (delete_remote=False)")

    # 3. Determine Uploads
    to_upload = []
    for rel_path, local_path in local_files.items():
        if delete_remote:
            if rel_path not in remote_keys:
                to_upload.append((local_path, prefix + rel_path))
        else:
            # If not deleting, we assume anything found in local_files (after time filter) is an upload candidate
            to_upload.append((local_path, prefix + rel_path))

    # 4. Determine Deletions (Remote exists but local doesn't) - Only if delete_remote is True
    to_delete = []
    if delete_remote:
        for rel_path, key in remote_keys.items():
            if rel_path not in local_files:
                to_delete.append(key)

    # 5. Execute
    if to_upload:
        logger.info(f"Uploading {len(to_upload)} files to {target_name}...")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for local_path, key in to_upload:
                executor.submit(upload_file, s3, bucket_name, local_path, key)

    if to_delete:
        logger.info(f"Deleting {len(to_delete)} stale files from remote {target_name}...")
        # S3 delete_objects has a 1000 limit
        for i in range(0, len(to_delete), 1000):
            batch = to_delete[i:i+1000]
            s3.delete_objects(
                Bucket=bucket_name,
                Delete={'Objects': [{'Key': k} for k in batch]}
            )

    # Save state
    state[state_key] = sync_start_time
    save_state(state)
    logger.info(f"Smart sync up for {target_name} complete.")