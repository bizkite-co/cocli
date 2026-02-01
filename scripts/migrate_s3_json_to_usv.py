import boto3
import json
import logging
import typer
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from cocli.models.website_domain_csv import WebsiteDomainCsv
from cocli.core.text_utils import slugdotify
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn

# Set logging to WARNING to silence individual file logs
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

app = typer.Typer()

def migrate_json_to_usv(s3_client: Any, bucket: str, key: str, delete_old: bool = False) -> None:
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        json_data = json.loads(response['Body'].read().decode('utf-8'))
        
        # Validate with Pydantic model
        item = WebsiteDomainCsv.model_validate(json_data)
        
        # New key with .usv extension and slugdotified domain
        usv_key = f"indexes/domains/{slugdotify(str(item.domain))}.usv"
        
        # Write USV content
        s3_client.put_object(
            Bucket=bucket, 
            Key=usv_key, 
            Body=item.to_usv().encode('utf-8'),
            ContentType="text/plain"
        )
        
        if delete_old and key != usv_key:
            s3_client.delete_object(Bucket=bucket, Key=key)
            
    except Exception as e:
        print(f"\n[ERROR] Failed to migrate {key}: {e}")

@app.command()
def main(
    bucket: str = typer.Argument(..., help="S3 Bucket name"),
    prefix: str = typer.Option("indexes/domains/", "--prefix", "-p", help="S3 Prefix"),
    workers: int = typer.Option(50, "--workers", "-w"),
    delete_old: bool = typer.Option(False, "--delete-old", help="Delete the original JSON files after conversion.")
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

    print(f"Migrating {len(json_keys)} files using {workers} workers...")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("({task.completed}/{task.total})"),
        TimeRemainingColumn(),
        auto_refresh=True,
    ) as progress:
        task = progress.add_task("[cyan]Processing...", total=len(json_keys))
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(migrate_json_to_usv, s3, bucket, key, delete_old) for key in json_keys]
            
            for _ in as_completed(futures):
                progress.advance(task)

    print("\n[bold green]Migration complete![/bold green]")

if __name__ == "__main__":
    app()
