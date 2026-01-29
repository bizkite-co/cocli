import boto3
import csv
import io
import logging
import typer
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from cocli.utils.usv_utils import USVWriter
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn

# Set logging to WARNING to silence individual file logs
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

app = typer.Typer()

def convert_csv_to_usv_bytes(csv_bytes: bytes) -> bytes:
    f_in = io.StringIO(csv_bytes.decode('utf-8'))
    reader = csv.reader(f_in)
    
    f_out = io.StringIO()
    writer = USVWriter(f_out)
    for row in reader:
        writer.writerow(row)
    
    return f_out.getvalue().encode('utf-8')

def migrate_object(s3_client: Any, bucket: str, key: str, delete_old: bool = False) -> None:
    usv_key = key[:-4] + ".usv"
    
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        csv_bytes = response['Body'].read()
        
        usv_bytes = convert_csv_to_usv_bytes(csv_bytes)
        
        s3_client.put_object(Bucket=bucket, Key=usv_key, Body=usv_bytes)
        
        if delete_old:
            s3_client.delete_object(Bucket=bucket, Key=key)
            
    except Exception as e:
        # We can use print here for errors specifically so they break through the progress bar silence
        print(f"\n[ERROR] Failed to migrate {key}: {e}")

@app.command()
def main(
    bucket: str = typer.Argument(..., help="S3 Bucket name"),
    prefix: str = typer.Argument("", help="S3 Prefix"),
    workers: int = typer.Option(50, "--workers", "-w"),
    delete_old: bool = typer.Option(False, "--delete-old", help="Delete the original CSV files after conversion.")
) -> None:
    s3 = boto3.client('s3')
    paginator = s3.get_paginator('list_objects_v2')
    
    csv_keys = set()
    usv_keys = set()
    
    print(f"Scanning s3://{bucket}/{prefix}...")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        if 'Contents' in page:
            for obj in page['Contents']:
                key = obj['Key']
                if key.endswith(".csv"):
                    csv_keys.add(key)
                elif key.endswith(".usv"):
                    usv_keys.add(key)
    
    # Filter out already migrated
    to_migrate = []
    for csv_key in csv_keys:
        usv_key = csv_key[:-4] + ".usv"
        if usv_key not in usv_keys:
            to_migrate.append(csv_key)
            
    print(f"Found {len(csv_keys)} CSVs. {len(usv_keys)} USVs already exist.")
    
    if not to_migrate:
        print("Nothing to migrate.")
        return

    print(f"Migrating {len(to_migrate)} files using {workers} workers...")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("({task.completed}/{task.total})"),
        TimeRemainingColumn(),
        auto_refresh=True,
    ) as progress:
        task = progress.add_task("[cyan]Processing...", total=len(to_migrate))
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            # Map futures
            futures = [executor.submit(migrate_object, s3, bucket, key, delete_old) for key in to_migrate]
            
            for _ in as_completed(futures):
                progress.advance(task)

    print("\n[bold green]Migration complete![/bold green]")

if __name__ == "__main__":
    app()
