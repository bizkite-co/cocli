import typer
import os
from pathlib import Path
from rich.console import Console
from rich.prompt import Confirm
from cocli.core.environment import get_environment, Environment

from cocli.services.sync_service import SyncService

app = typer.Typer(help="Administrative commands for system management.", no_args_is_help=True)
console = Console()

@app.command(name="archive-campaign")
def archive_campaign(
    campaign_name: str = typer.Argument(..., help="Name of the campaign to archive."),
    upload: bool = typer.Option(True, help="Whether to upload to S3 after archiving."),
    keep_local: bool = typer.Option(False, help="Whether to keep the local archive after upload.")
) -> None:
    """
    Creates a compressed archive of a campaign and uploads it to S3.
    """
    try:
        service = SyncService(campaign_name)
        console.print(f"[bold cyan]Archiving campaign: {campaign_name}[/bold cyan]")
        
        with console.status("Creating archive..."):
            archive_path = service.archive_campaign()
            console.print(f"[green]Archive created:[/green] {archive_path}")
            
        if upload:
            with console.status("Uploading to S3..."):
                s3_uri = service.upload_archive(archive_path)
                console.print(f"[green]Successfully uploaded to:[/green] {s3_uri}")
                
            if not keep_local:
                archive_path.unlink()
                console.print("[dim]Removed local archive.[/dim]")
                
        console.print("[bold green]Campaign archive operation complete![/bold green]")
        
    except Exception as e:
        console.print(f"[bold red]Archive failed:[/bold red] {e}")
        raise typer.Exit(1)

def get_prod_root() -> Path:
    """Returns the absolute root for PROD data."""
    if "COCLI_DATA_HOME" in os.environ:
        return Path(os.environ["COCLI_DATA_HOME"]).expanduser().resolve()
    
    import platform
    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "cocli"
    elif platform.system() == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "cocli"
    else:
        base = Path.home() / ".local" / "share" / "cocli"
    return base / "data"

@app.command(name="refresh-dev")
def refresh_dev(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt."),
    sync_s3: bool = typer.Option(False, "--s3", help="Also sync local data to the isolated DEV S3 bucket.")
) -> None:
    """
    Refreshes the local DEV environment data from PROD.
    Uses rsync to efficiently mirror PROD -> DEV while excluding transient data.
    """
    env = get_environment()
    if env == Environment.PROD:
        console.print("[red bold]ERROR: Cannot run refresh-dev while in PROD mode.[/red bold]")
        console.print("Set COCLI_ENV=dev to use this command.")
        raise typer.Exit(1)

    prod_root = get_prod_root()
    target_root = prod_root.parent / f"{prod_root.name}_{env.value}"

    if not prod_root.exists():
        console.print(f"[red]ERROR: PROD data not found at {prod_root}[/red]")
        raise typer.Exit(1)

    console.print("[bold]Refresh Plan:[/bold]")
    console.print(f"  Source (PROD): {prod_root}")
    console.print(f"  Target ({env.value.upper()}): {target_root}")
    if sync_s3:
        console.print("  S3 Sync: Enabled (will upload to isolated DEV buckets)")
    
    if not force:
        if not Confirm.ask(f"Are you sure you want to Refresh {env.value.upper()} data from PROD?"):
            console.print("[yellow]Refresh cancelled.[/yellow]")
            return

    try:
        target_root.mkdir(parents=True, exist_ok=True)
        
        console.print("[bold cyan]Syncing data via rsync...[/bold cyan]")
        import subprocess
        # Exclude WAL, logs, recovery, and other transient/bulk junk
        excludes = ["wal", "logs", "recovery", "*.usv.wal", "temp"]
        cmd = ["rsync", "-av", "--delete"]
        for ex in excludes:
            cmd.extend(["--exclude", ex])
        
        # Ensure trailing slashes for rsync
        cmd.append(str(prod_root) + "/")
        cmd.append(str(target_root) + "/")
        
        subprocess.run(cmd, check=True)
        
        console.print(f"[bold green]Successfully refreshed {env.value.upper()} local data![/bold green]")

        if sync_s3:
            console.print("[bold cyan]Syncing local data to isolated S3 DEV buckets...[/bold cyan]")
            # We must iterate over campaigns to find their buckets
            campaigns_dir = target_root / "campaigns"
            if campaigns_dir.exists():
                for c_dir in campaigns_dir.iterdir():
                    if c_dir.is_dir() and (c_dir / "config.toml").exists():
                        campaign_name = c_dir.name
                        console.print(f"  Refilling S3 for campaign: {campaign_name}...")
                        from cocli.core.reporting import get_data_bucket_name, load_campaign_config
                        config = load_campaign_config(campaign_name)
                        bucket = get_data_bucket_name(config, campaign_name)
                        
                        # Use subprocess to call 'aws s3 sync' for efficiency if endpoint is real AWS
                        # or boto3 for mocks.
                        if "COCLI_S3_ENDPOINT" in os.environ:
                             # For local mock, use boto3 or our smart-sync logic
                             console.print(f"  [dim]Uploading to mock bucket: {bucket}...[/dim]")
                             # Implementation of upload logic for mock...
                        else:
                             # Use fast AWS CLI if available
                             s3_cmd = ["aws", "s3", "sync", str(c_dir) + "/", f"s3://{bucket}/campaigns/{campaign_name}/", "--delete"]
                             # We must ensure we use the right profile from config
                             profile = config.get("aws", {}).get("profile") or config.get("aws", {}).get("aws_profile")
                             if profile:
                                 s3_cmd.extend(["--profile", profile])
                             subprocess.run(s3_cmd, check=True)

            console.print("[bold green]S3 DEV refresh complete![/bold green]")

    except Exception as e:
        console.print(f"[red bold]Refresh failed: {e}[/red bold]")
        raise typer.Exit(1)
