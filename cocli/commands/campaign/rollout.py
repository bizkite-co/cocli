# POLICY: frictionless-data-policy-enforcement
import typer
import asyncio
import logging
from typing import Optional, Annotated
from rich.console import Console

from cocli.core.config import get_campaign
from cocli.application.operation_service import OperationService

logger = logging.getLogger(__name__)
console = Console()
app = typer.Typer(name="rollout", help="Standardized campaign rollout management.", no_args_is_help=True)

@app.command(name="run")
def run_rollout(
    campaign_name: Annotated[Optional[str], typer.Argument(help="The name of the campaign.")] = None,
    name: str = typer.Option("canary", help="Name of the batch (e.g., 'canary', 'rollout_1')"),
    limit: int = typer.Option(50, help="Number of items to include in the batch"),
    ttl_days: int = typer.Option(30, help="Items scraped longer than this many days ago are considered stale."),
    force: bool = typer.Option(False, "--force", "-f", help="Force rescrape of all items in the batch (sets TTL to 0)."),
    purge: bool = typer.Option(False, "--purge", help="Purge the existing active task pool before starting (Clean Start)."),
    monitor: bool = typer.Option(True, "--monitor/--no-monitor", help="Automatically start monitoring after rollout."),
) -> None:
    """
    Executes a standardized discovery rollout:
    1. Create Batch -> 2. Build Mission Index -> 3. Push to Cluster
    """
    if campaign_name is None:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    effective_ttl = 0 if force else ttl_days
    op_service = OperationService(campaign_name)
    
    async def run() -> None:
        params = {
            "batch_name": name, 
            "limit": limit, 
            "ttl_days": effective_ttl,
            "purge": purge
        }
        
        def log_cb(msg: str) -> None:
            console.print(msg, end="")

        result = await op_service.execute("op_rollout_discovery", log_callback=log_cb, params=params)
        
        if result["status"] == "success":
            console.print(f"\n[bold green]Rollout '{name}' successful![/bold green]")
            if monitor:
                console.print(f"[cyan]Starting cluster monitor for batch: {name}...[/cyan]")
                # We can't easily 'chain' the monitor command here because it's synchronous/interactive
                # but we can give the user the command to run.
                console.print(f"\nRun: [bold white]cocli campaign monitor-batch {campaign_name} --name {name} --cluster[/bold white]")
        else:
            console.print(f"\n[bold red]Rollout failed: {result.get('message')}[/bold red]")

    asyncio.run(run())

@app.command(name="broadcast-config")
def broadcast_config(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name."),
) -> None:
    """
    Broadcasts the current scaling configuration to all cluster nodes via Gossip.
    Triggers near-instantaneous worker re-balancing.
    """
    effective_campaign = campaign or get_campaign()
    if not effective_campaign:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    import toml
    import time
    from cocli.core.paths import paths
    from cocli.core.gossip_bridge import bridge
    from cocli.models.wal.record import ConfigDatagram
    import json

    config_path = paths.campaign(effective_campaign).path / "config.toml"
    if not config_path.exists():
        console.print(f"[red]Config not found at {config_path}[/red]")
        raise typer.Exit(1)

    with open(config_path, "r") as f:
        config = toml.load(f)
    
    scaling = config.get("prospecting", {}).get("scaling", {})
    if not scaling:
        console.print("[yellow]No scaling configuration found in config.toml[/yellow]")
        return

    # Create Broadcast Datagram
    datagram = ConfigDatagram(
        node_id="*", # Broadcast to all
        config_json=json.dumps(scaling),
        timestamp=str(int(time.time()))
    )

    console.print(f"[bold cyan]Broadcasting scaling update for {effective_campaign}...[/bold cyan]")
    
    # We need to start the bridge briefly to send
    bridge.start()
    time.sleep(2) # Give it a moment to discover peers from config
    bridge.broadcast_msg(datagram.to_usv())
    time.sleep(1) # Ensure it's sent
    bridge.stop()
    
    console.print("[bold green]Broadcast complete.[/bold green]")

@app.command(name="push")
def push_data(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name."),
    delete: bool = typer.Option(False, "--delete", help="Delete remote files not present locally."),
) -> None:
    """
    Propagates local campaign discovery tasks and batches to the cluster.
    (Moved from 'cluster push-data' for campaign-centric workflow)
    """
    effective_campaign = campaign or get_campaign()
    if not effective_campaign:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    from cocli.services.cluster_service import ClusterService
    service = ClusterService(effective_campaign)
    
    async def run() -> None:
        await service.push_data(delete=delete)
        console.print("[bold green]Data propagated to cluster.[/bold green]")

    asyncio.run(run())

@app.command(name="audit")
def sync_audit(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name."),
) -> None:
    """
    Pulls results from all cluster nodes and runs a quality audit.
    (Moved from 'cluster sync-audit' for campaign-centric workflow)
    """
    effective_campaign = campaign or get_campaign()
    if not effective_campaign:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    from cocli.services.cluster_service import ClusterService
    service = ClusterService(effective_campaign)
    
    async def run() -> None:
        await service.sync_and_audit()

    asyncio.run(run())

if __name__ == "__main__":
    app()
