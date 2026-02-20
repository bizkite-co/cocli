import boto3
import json
import logging
import typer
import uuid
import hashlib
from typing import Any, Dict
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from cocli.models.campaigns.indexes.domains import WebsiteDomainCsv
from cocli.models.index_manifest import IndexManifest, IndexShard
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn

# Set logging to WARNING to silence individual file logs
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

app = typer.Typer()

def get_shard_id(domain: str) -> str:
    """Calculates a deterministic shard ID (00-ff) based on domain hash."""
    return hashlib.sha256(domain.encode()).hexdigest()[:2]

def download_and_parse(s3_client: Any, bucket: str, key: str) -> WebsiteDomainCsv | None:
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        json_data = json.loads(response['Body'].read().decode('utf-8'))
        return WebsiteDomainCsv.model_validate(json_data)
    except Exception as e:
        logger.error(f"Failed to process {key}: {e}")
        return None

@app.command()
def main(
    bucket: str = typer.Argument(..., help="S3 Bucket name"),
    prefix: str = typer.Option("indexes/domains/", "--prefix", "-p", help="S3 Prefix for source JSON files"),
    workers: int = typer.Option(50, "--workers", "-w"),
) -> None:
    s3 = boto3.client('s3')
    paginator = s3.get_paginator('list_objects_v2')
    
    json_keys = []
    print(f"Scanning s3://{bucket}/{prefix}...")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        if 'Contents' in page:
            for obj in page['Contents']:
                key = obj['Key']
                if key.endswith(".json") and not key.split('/')[-1].startswith("_"):
                    json_keys.append(key)
    
    if not json_keys:
        print("No JSON files found to migrate.")
        return

    print(f"Downloading and sharding {len(json_keys)} files using {workers} workers...")

    shard_data: Dict[str, Dict[str, WebsiteDomainCsv]] = {f"{i:02x}": {} for i in range(256)}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("({task.completed}/{task.total})"),
        TimeRemainingColumn(),
        auto_refresh=True,
    ) as progress:
        task = progress.add_task("[cyan]Downloading...", total=len(json_keys))
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(download_and_parse, s3, bucket, key) for key in json_keys]
            
            for future in as_completed(futures):
                item = future.result()
                if item:
                    shard_id = get_shard_id(str(item.domain))
                    # Deduplicate: latest wins
                    if item.domain not in shard_data[shard_id] or item.updated_at > shard_data[shard_id][item.domain].updated_at:
                        shard_data[shard_id][str(item.domain)] = item
                progress.advance(task)

    print("\nWriting shards to S3...")
    manifest = IndexManifest()
    shards_prefix = "indexes/domains/shards/"

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        auto_refresh=True,
    ) as progress:
        write_task = progress.add_task("[green]Uploading Shards...", total=256)
        
        for shard_id, items in shard_data.items():
            if not items:
                progress.advance(write_task)
                continue
            
            shard_key = f"{shards_prefix}{shard_id}.usv"
            shard_content = "\n".join([item.to_usv() for item in items.values()]) + "\n"
            
            s3.put_object(
                Bucket=bucket,
                Key=shard_key,
                Body=shard_content.encode('utf-8'),
                ContentType="text/plain"
            )
            
            manifest.shards[shard_id] = IndexShard(
                path=shard_key,
                record_count=len(items),
                schema_version=6,
                updated_at=datetime.now(timezone.utc)
            )
            progress.advance(write_task)

    print("\nFinalizing Manifest...")
    manifest_id = str(uuid.uuid4())
    manifest_key = f"indexes/domains/manifests/{manifest_id}.usv"
    s3.put_object(
        Bucket=bucket,
        Key=manifest_key,
        Body=manifest.to_usv().encode('utf-8'),
        ContentType="text/plain"
    )
    
    s3.put_object(
        Bucket=bucket,
        Key="indexes/domains/LATEST",
        Body=manifest_key.encode('utf-8'),
        ContentType="text/plain"
    )

    print("\n[bold green]Migration complete![/bold green]")
    print(f"Manifest: {manifest_key}")
    print(f"Total domains sharded: {sum(s.record_count for s in manifest.shards.values())}")

if __name__ == "__main__":
    app()
