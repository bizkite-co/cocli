import boto3
import logging
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

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
    delete_remote: bool = False
) -> None:
    logger.info(f"Starting smart sync UP for {target_name} to s3://{bucket_name}/{prefix}")
    profile_name = aws_config.get("profile") or aws_config.get("aws_profile")
    try:
        if profile_name:
            session = boto3.Session(profile_name=profile_name)
        else:
            session = boto3.Session()
        s3 = session.client("s3")
    except Exception as e:
         logger.error(f"Failed to create AWS session for upload: {e}")
         return

    # 1. List Local Files
    local_files = {}
    if local_base.exists():
        logger.info(f"Scanning local directory: {local_base}")
        for path in local_base.rglob("*"):
            if path.is_file():
                rel_path = path.relative_to(local_base)
                local_files[str(rel_path)] = path
    else:
        logger.warning(f"Local base directory does not exist: {local_base}")

    # 2. List Remote Files
    remote_keys = {}
    logger.debug(f"Scanning S3 prefix: s3://{bucket_name}/{prefix}")
    paginator = s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)
    for page in pages:
        if 'Contents' in page:
            for obj in page['Contents']:
                key = obj['Key']
                rel_path = key[len(prefix):] if key.startswith(prefix) else key
                remote_keys[rel_path] = key

    # 3. Determine Uploads (Local exists but remote doesn't OR local is newer)
    to_upload = []
    for rel_path, local_path in local_files.items():
        if rel_path not in remote_keys:
            to_upload.append((local_path, prefix + rel_path))
        else:
            # Check mtime (S3 mtime is UTC)
            s3_mtime = s3.head_object(Bucket=bucket_name, Key=remote_keys[rel_path])['LastModified']
            if local_path.stat().st_mtime > s3_mtime.timestamp():
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

    logger.info(f"Smart sync up for {target_name} complete.")
