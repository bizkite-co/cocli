import typer
import boto3
import os
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, Tuple
from cocli.core.config import get_cocli_base_dir, load_campaign_config

console = Console()
app = typer.Typer()

DATA_DIR = get_cocli_base_dir()

def upload_file(s3_client, bucket: str, local_path: Path, s3_key: str, progress, task_id):
    try:
        # Check if file exists on S3 and compare size/mtime if needed?
        # For queue pushing, we generally assume we want to push what we have.
        # To be safe/efficient, we can check head_object.
        
        should_upload = True
        try:
            head = s3_client.head_object(Bucket=bucket, Key=s3_key)
            if head['ContentLength'] == local_path.stat().st_size:
                should_upload = False
        except:
            # Object doesn't exist
            pass

        if should_upload:
            s3_client.upload_file(str(local_path), bucket, s3_key)
        
        progress.advance(task_id, 1)
    except Exception as e:
        console.print(f"[red]Error uploading {local_path}: {e}[/red]")

@app.command()
def main(
    campaign: str = typer.Option("turboship", help="Campaign name"),
    queue: str = typer.Option("enrichment", help="Queue name (e.g., enrichment, gm-list)"),
    workers: int = typer.Option(50, help="Number of concurrent upload threads"),
):
    """
    Push local queue items to S3 with a progress bar.
    """
    config = load_campaign_config(campaign)
    aws_config = config.get("aws", {})
    bucket_name = aws_config.get("cocli_data_bucket_name") or f"cocli-data-{campaign}"
    profile_name = aws_config.get("profile") or aws_config.get("aws_profile")

    session = boto3.Session(profile_name=profile_name)
    s3 = session.client("s3")

    # Local Path
    # Support both V1 and V2 structures? 
    # V2: data/queues/<campaign>/<queue>/pending/
    local_queue_dir = DATA_DIR / "data" / "queues" / campaign / queue / "pending"
    
    if not local_queue_dir.exists():
        console.print(f"[red]Queue directory not found: {local_queue_dir}[/red]")
        raise typer.Exit(1)

    # S3 Prefix
    s3_prefix = f"campaigns/{campaign}/queues/{queue}/pending/"

    console.print(f"[bold blue]Scanning local queue: {local_queue_dir}[/bold blue]")
    
    files_to_upload: List[Tuple[Path, str]] = []
    
    # Walk the directory
    with console.status("[bold green]Collecting files...[/bold green]"):
        for root, _, files in os.walk(local_queue_dir):
            for file in files:
                local_path = Path(root) / file
                rel_path = local_path.relative_to(local_queue_dir)
                s3_key = f"{s3_prefix}{rel_path}"
                files_to_upload.append((local_path, s3_key))

    total_files = len(files_to_upload)
    console.print(f"Found {total_files} files to check/upload.")

    if total_files == 0:
        return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task(f"Pushing to s3://{bucket_name}...", total=total_files)
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(upload_file, s3, bucket_name, local, key, progress, task_id) 
                for local, key in files_to_upload
            ]
            for f in futures:
                f.result()

    console.print("[bold green]Upload Complete![/bold green]")

if __name__ == "__main__":
    app()
