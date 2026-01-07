import typer
from typing import Optional
from rich.console import Console
from cocli.core.infrastructure.rpi import deploy_rpi_credentials, start_rpi_worker, stop_rpi_workers
from cocli.core.config import get_campaign, load_campaign_config

app = typer.Typer(help="Manage cocli infrastructure (Raspberry Pis, AWS).")
console = Console()

@app.command()
def deploy_creds(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name to use for profile resolution."),
    host: Optional[str] = typer.Option(None, "--host", help="Specific RPi host to deploy to."),
    user: str = typer.Option("mstouffer", "--user", "-u", help="SSH user for the RPi.")
) -> None:
    """
    Deploys AWS credentials for the active campaign to Raspberry Pi cluster members.
    """
    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print("[bold red]Error:[/bold red] No campaign specified and no active context.")
        raise typer.Exit(1)

    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    profile = aws_config.get("profile") or aws_config.get("aws_profile")

    if not profile:
        console.print(f"[bold red]Error:[/bold red] No AWS profile configured for campaign '{campaign_name}'.")
        raise typer.Exit(1)

    # Determine hosts
    hosts = [host] if host else ["octoprint.local", "cocli5x0.local"]
    
    success = True
    for h in hosts:
        if not deploy_rpi_credentials(profile, h, user):
            success = False
    
    if not success:
        raise typer.Exit(1)

@app.command()
def stop_workers(
    host: str = typer.Argument(..., help="Host to stop workers on."),
    user: str = typer.Option("mstouffer", "--user", "-u", help="SSH user for the RPi.")
) -> None:
    """Stops all cocli workers on a specific host."""
    stop_rpi_workers(host, user)

@app.command()
def start_worker(
    host: str = typer.Argument(..., help="Host to start worker on."),
    role: str = typer.Option("scrape", "--role", help="Worker role: 'scrape' or 'details'"),
    workers: int = typer.Option(1, "--count", "-n", help="Number of concurrent worker threads."),
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name."),
    user: str = typer.Option("mstouffer", "--user", "-u", help="SSH user for the RPi.")
) -> None:
    """Starts a cocli worker role on a specific host."""
    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print("[bold red]Error:[/bold red] No campaign specified.")
        raise typer.Exit(1)

    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    profile = aws_config.get("profile") or aws_config.get("aws_profile") or "default"

    # Resolve Queues
    queues = {
        "COCLI_SCRAPE_TASKS_QUEUE_URL": aws_config.get("cocli_scrape_tasks_queue_url"),
        "COCLI_GM_LIST_ITEM_QUEUE_URL": aws_config.get("cocli_gm_list_item_queue_url"),
        "COCLI_ENRICHMENT_QUEUE_URL": aws_config.get("cocli_enrichment_queue_url")
    }
    # Filter out missing ones
    queues = {k: v for k, v in queues.items() if v}

    start_rpi_worker(host, campaign_name, role, profile, queues, user, workers)

if __name__ == "__main__":
    app()
