import boto3
import logging
import typer
from botocore.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = typer.Typer()

@app.command()
def main(
    bucket: str = typer.Argument(..., help="S3 Bucket name"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run"),
) -> None:
    s3 = boto3.client('s3', config=Config(max_pool_connections=50))
    prefix = "indexes/domains/"
    
    print(f"Scanning s3://{bucket}/{prefix} for junk...")
    
    # We want to keep:
    # 1. indexes/domains/shards/
    # 2. indexes/domains/manifests/
    # 3. indexes/domains/LATEST
    # 4. indexes/domains/*.usv (Current Inbox)
    
    keep_prefixes = ["indexes/domains/shards/", "indexes/domains/manifests/"]
    keep_files = ["indexes/domains/LATEST"]
    
    paginator = s3.get_paginator('list_objects_v2')
    
    delete_keys = []
    
    # List all objects under the prefix
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        if 'Contents' in page:
            for obj in page['Contents']:
                key = obj['Key']
                
                # Check if it's in a keep prefix
                if any(key.startswith(p) for p in keep_prefixes):
                    continue
                
                # Check if it's a keep file
                if key in keep_files:
                    continue
                
                # Check if it's a valid inbox file (.usv and matches slugdotify)
                # For now, let's just say any .usv in the root is an inbox file
                if key.endswith(".usv") and "/" not in key.replace(prefix, ""):
                    continue
                
                # Everything else is junk
                delete_keys.append(key)

    if not delete_keys:
        print("No junk found.")
        return

    print(f"Found {len(delete_keys)} junk objects.")
    
    if dry_run:
        for key in delete_keys[:10]:
            print(f"  [DRY-RUN] Would delete: {key}")
        if len(delete_keys) > 10:
            print(f"  ... and {len(delete_keys)-10} more.")
        print("\nDRY RUN: No files deleted. Use --no-dry-run to execute.")
    else:
        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task("[red]Deleting junk...", total=len(delete_keys))
            
            # Batch delete in 1000s
            for i in range(0, len(delete_keys), 1000):
                batch = delete_keys[i:i+1000]
                s3.delete_objects(
                    Bucket=bucket,
                    Delete={
                        'Objects': [{'Key': k} for k in batch]
                    }
                )
                progress.advance(task, len(batch))
        print("Done.")

if __name__ == "__main__":
    app()
