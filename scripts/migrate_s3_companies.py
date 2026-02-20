import boto3
import typer
import logging
from rich.console import Console
from rich.progress import Progress
from cocli.core.config import load_campaign_config
from cocli.core.paths import paths

app = typer.Typer()
console = Console()
logger = logging.getLogger(__name__)

def migrate_companies(campaign_name: str, dry_run: bool = True) -> None:
    config = load_campaign_config(campaign_name)
    bucket = config.get("aws", {}).get("data_bucket_name")
    
    if not bucket:
        console.print(f"[bold red]Error:[/bold red] data_bucket_name not found for campaign {campaign_name}")
        return

    s3 = boto3.client("s3")
    
    # Legacy prefix: "companies/"
    legacy_prefix = "companies/"
    # New prefix: "campaigns/<campaign>/companies/"
    new_prefix = paths.s3.campaign(campaign_name).root + "companies/"
    
    console.print(f"Migrating from [cyan]{legacy_prefix}[/cyan] to [green]{new_prefix}[/green] in bucket [bold]{bucket}[/bold]")
    if dry_run:
        console.print("[yellow]DRY RUN ENABLED - No files will be moved.[/yellow]")

    paginator = s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket, Prefix=legacy_prefix)

    total_moved = 0
    
    with Progress() as progress:
        task = progress.add_task("Moving objects...", total=None)
        
        for page in pages:
            if 'Contents' not in page:
                continue
                
            for obj in page['Contents']:
                old_key = obj['Key']
                # Skip the prefix itself
                if old_key == legacy_prefix:
                    continue
                
                # Construct new key
                relative_path = old_key[len(legacy_prefix):]
                new_key = new_prefix + relative_path
                
                if dry_run:
                    logger.info(f"WOULD MOVE: {old_key} -> {new_key}")
                else:
                    # S3 move is COPY + DELETE
                    s3.copy_object(
                        Bucket=bucket,
                        CopySource={'Bucket': bucket, 'Key': old_key},
                        Key=new_key
                    )
                    s3.delete_object(Bucket=bucket, Key=old_key)
                    logger.debug(f"MOVED: {old_key} -> {new_key}")
                
                total_moved += 1
                progress.update(task, advance=1, description=f"Moved {total_moved} objects")

    console.print(f"[bold green]Migration complete.[/bold green] Total objects processed: {total_moved}")

@app.command()
def run(
    campaign: str = typer.Argument(..., help="Campaign name"),
    execute: bool = typer.Option(False, "--execute", help="Actually perform the move (not dry-run)")
) -> None:
    migrate_companies(campaign, dry_run=not execute)

if __name__ == "__main__":
    app()
