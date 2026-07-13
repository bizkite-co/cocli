import typer
import logging
from rich.console import Console
from typing import Optional

from ..core.config import get_cocli_base_dir
from ..core.reporting import get_data_bucket_name

console = Console()
app = typer.Typer(no_args_is_help=True)

DATA_DIR = get_cocli_base_dir()
STATE_FILE = DATA_DIR / ".smart_sync_state.json"

logger = logging.getLogger(__name__)

from ..core.smart_sync import run_smart_sync

@app.command("companies")
def sync_companies(
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name"),
    workers: int = typer.Option(20, help="Number of concurrent download threads."),
    full: bool = typer.Option(False, "--full", help="Perform a full integrity check (slower)."),
    force: bool = typer.Option(False, "--force", help="Force download all files."),
) -> None:
    from ..core.config import get_campaign, load_campaign_config
    campaign_name = campaign_name or get_campaign()
    if not campaign_name:
        console.print("[bold red]No campaign specified.[/bold red]")
        raise typer.Exit(1)
    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    bucket_name = get_data_bucket_name(config, campaign_name)
    run_smart_sync("companies", bucket_name, "companies/", DATA_DIR / "companies", campaign_name, aws_config, workers, full, force)

@app.command("prospects")
def sync_prospects(
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name"),
    workers: int = typer.Option(20, help="Number of concurrent download threads."),
    full: bool = typer.Option(False, "--full", help="Perform a full integrity check (slower)."),
    force: bool = typer.Option(False, "--force", help="Force download all files."),
) -> None:
    from ..core.config import get_campaign, load_campaign_config
    campaign_name = campaign_name or get_campaign()
    if not campaign_name:
        console.print("[bold red]No campaign specified.[/bold red]")
        raise typer.Exit(1)
    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    bucket_name = get_data_bucket_name(config, campaign_name)
    prefix = f"campaigns/{campaign_name}/indexes/google_maps_prospects/"
    local_base = DATA_DIR / "campaigns" / campaign_name / "indexes" / "google_maps_prospects"
    run_smart_sync("prospects", bucket_name, prefix, local_base, campaign_name, aws_config, workers, full, force)

@app.command("emails")
def sync_emails(
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name"),
    workers: int = typer.Option(20, help="Number of concurrent download threads."),
    full: bool = typer.Option(False, "--full", help="Perform a full integrity check (slower)."),
    force: bool = typer.Option(False, "--force", help="Force download all files."),
) -> None:
    from ..core.config import get_campaign, load_campaign_config
    campaign_name = campaign_name or get_campaign()
    if not campaign_name:
        console.print("[bold red]No campaign specified.[/bold red]")
        raise typer.Exit(1)
    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    bucket_name = get_data_bucket_name(config, campaign_name)
    prefix = f"campaigns/{campaign_name}/indexes/emails/"
    local_base = DATA_DIR / "campaigns" / campaign_name / "indexes" / "emails"
    run_smart_sync("emails", bucket_name, prefix, local_base, campaign_name, aws_config, workers, full, force)

@app.command("scraped-areas")
def sync_scraped_areas(
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name"),
    workers: int = typer.Option(20, help="Number of concurrent download threads."),
    full: bool = typer.Option(False, "--full", help="Perform a full integrity check (slower)."),
    force: bool = typer.Option(False, "--force", help="Force download all files."),
) -> None:
    from ..core.config import get_campaign, load_campaign_config
    campaign_name = campaign_name or get_campaign()
    if not campaign_name:
        console.print("[bold red]No campaign specified.[/bold red]")
        raise typer.Exit(1)
    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    bucket_name = get_data_bucket_name(config, campaign_name)
    run_smart_sync("scraped-areas", bucket_name, "indexes/scraped_areas/", DATA_DIR / "indexes" / "scraped_areas", campaign_name, aws_config, workers, full, force)

@app.command("scraped-tiles")
def sync_scraped_tiles(
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name"),
    workers: int = typer.Option(20, help="Number of concurrent download threads."),
    full: bool = typer.Option(False, "--full", help="Perform a full integrity check (slower)."),
    force: bool = typer.Option(False, "--force", help="Force download all files."),
) -> None:
    from ..core.config import get_campaign, load_campaign_config
    campaign_name = campaign_name or get_campaign()
    if not campaign_name:
        console.print("[bold red]No campaign specified.[/bold red]")
        raise typer.Exit(1)
    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    bucket_name = get_data_bucket_name(config, campaign_name)
    run_smart_sync("scraped-tiles", bucket_name, "indexes/scraped-tiles/", DATA_DIR / "indexes" / "scraped-tiles", campaign_name, aws_config, workers, full, force)

@app.command("enrichment-queue")
def sync_enrichment_queue(
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name"),
    workers: int = typer.Option(20, help="Number of concurrent download threads."),
    full: bool = typer.Option(False, "--full", help="Perform a full integrity check (slower)."),
    force: bool = typer.Option(False, "--force", help="Force download all files."),
) -> None:
    from ..core.config import get_campaign, load_campaign_config
    campaign_name = campaign_name or get_campaign()
    if not campaign_name:
        console.print("[bold red]No campaign specified.[/bold red]")
        raise typer.Exit(1)
    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    bucket_name = get_data_bucket_name(config, campaign_name)
    
    # V2 Path
    from ..core.paths import paths
    prefix = f"campaigns/{campaign_name}/queues/enrichment/pending/"
    local_base = paths.queue(campaign_name, "enrichment") / "pending"
    run_smart_sync("enrichment-queue", bucket_name, prefix, local_base, campaign_name, aws_config, workers, full, force)

@app.command("active-leases")
def sync_active_leases(
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name"),
    workers: int = typer.Option(20, help="Number of concurrent download threads."),
    full: bool = typer.Option(False, "--full", help="Perform a full integrity check (slower)."),
    force: bool = typer.Option(False, "--force", help="Force download all files."),
) -> None:
    from ..core.config import get_campaign, load_campaign_config
    campaign_name = campaign_name or get_campaign()
    if not campaign_name:
        console.print("[bold red]No campaign specified.[/bold red]")
        raise typer.Exit(1)
    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    bucket_name = get_data_bucket_name(config, campaign_name)
    
    # V2 Path - In V2, leases are mixed in with pending tasks
    from ..core.paths import paths
    prefix = f"campaigns/{campaign_name}/queues/enrichment/pending/"
    local_base = paths.queue(campaign_name, "enrichment") / "pending"
    run_smart_sync("active-leases", bucket_name, prefix, local_base, campaign_name, aws_config, workers, full, force)

@app.command("raw")
def sync_raw(
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name"),
    workers: int = typer.Option(20, help="Number of concurrent download threads."),
    full: bool = typer.Option(False, "--full", help="Perform a full integrity check."),
    force: bool = typer.Option(False, "--force", help="Force download all files."),
) -> None:
    """Syncs raw HTML witnesses (both details and list items) from S3."""
    from ..core.config import get_campaign, load_campaign_config
    campaign_name = campaign_name or get_campaign()
    if not campaign_name:
        console.print("[bold red]No campaign specified.[/bold red]")
        raise typer.Exit(1)
    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    bucket_name = get_data_bucket_name(config, campaign_name)
    
    # 1. Sync Details Raw
    prefix_details = f"campaigns/{campaign_name}/raw/gm-details/"
    local_base_details = DATA_DIR / "campaigns" / campaign_name / "raw" / "gm-details"
    run_smart_sync("raw-details", bucket_name, prefix_details, local_base_details, campaign_name, aws_config, workers, full, force)

    # 2. Sync List Raw
    prefix_list = f"campaigns/{campaign_name}/raw/gm-list/"
    local_base_list = DATA_DIR / "campaigns" / campaign_name / "raw" / "gm-list"
    run_smart_sync("raw-list", bucket_name, prefix_list, local_base_list, campaign_name, aws_config, workers, full, force)

@app.command("queues")
def sync_queues(
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name"),
    workers: int = typer.Option(20, help="Number of concurrent download threads."),
    full: bool = typer.Option(False, "--full", help="Perform a full integrity check (slower)."),
    force: bool = typer.Option(False, "--force", help="Force download all files."),
) -> None:
    from ..core.config import get_campaign, load_campaign_config
    campaign_name = campaign_name or get_campaign()
    if not campaign_name:
        console.print("[bold red]No campaign specified.[/bold red]")
        raise typer.Exit(1)
    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    bucket_name = get_data_bucket_name(config, campaign_name)
    
    from ..core.paths import paths
    for q in ["map-tile", "gm-list", "gm-details", "enrichment"]:
        # Completed Path (Used for zombie check)
        local_base_completed = paths.queue(campaign_name, q) / "completed"

        # Pending
        prefix = f"campaigns/{campaign_name}/queues/{q}/pending/"
        local_base_pending = paths.queue(campaign_name, q) / "pending"
        run_smart_sync(f"{q}-pending", bucket_name, prefix, local_base_pending, campaign_name, aws_config, workers, full, force, completed_dir=local_base_completed)
        
        # Completed (Optional sync down if needed for reporting)
        prefix = f"campaigns/{campaign_name}/queues/{q}/completed/"
        run_smart_sync(f"{q}-completed", bucket_name, prefix, local_base_completed, campaign_name, aws_config, workers, full, force)

@app.command("campaign-config")
def sync_campaign_config(
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name"),
) -> None:
    from ..core.config import get_campaign, load_campaign_config
    campaign_name = campaign_name or get_campaign()
    if not campaign_name:
        console.print("[bold red]No campaign specified.[/bold red]")
        raise typer.Exit(1)
    
    # Try to load existing config to get the correct bucket name
    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    bucket_name = get_data_bucket_name(config, campaign_name)
    
    prefix = f"campaigns/{campaign_name}/"
    local_base = DATA_DIR / "campaigns" / campaign_name
    
    run_smart_sync("campaign-config", bucket_name, prefix, local_base, campaign_name, aws_config, workers=1)

@app.command("all")
def sync_all(
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name"),
    workers: int = typer.Option(20, help="Number of concurrent download threads."),
    full: bool = typer.Option(False, "--full", help="Perform a full integrity check."),
    force: bool = typer.Option(False, "--force", help="Force download all files."),
) -> None:
    """Syncs everything for a campaign (Config, Prospects, Emails, and Queues)."""
    from ..core.config import get_campaign
    campaign_name = campaign_name or get_campaign()
    if not campaign_name:
        console.print("[bold red]No campaign specified.[/bold red]")
        raise typer.Exit(1)

    console.print(f"[bold cyan]Starting FULL sync for campaign: {campaign_name}[/bold cyan]")
    
    # 1. Config
    sync_campaign_config(campaign_name)
    
    # 2. Prospects
    sync_prospects(campaign_name, workers, full, force)
    
    # 3. Emails
    sync_emails(campaign_name, workers, full, force)
    
    # 4. Queues
    sync_queues(campaign_name, workers, full, force)
    
    console.print(f"[bold green]FULL campaign sync complete for {campaign_name}![/bold green]")

if __name__ == "__main__":
    app()