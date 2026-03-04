# POLICY: frictionless-data-policy-enforcement
import typer
import asyncio
import os
from typing import Optional
from rich.console import Console
from rich.table import Table

from ..services.cluster_service import ClusterService
from ..core.config import get_campaign
from ..core.logging_config import setup_file_logging

console = Console()
app = typer.Typer(name="cluster", help="Manage the Raspberry Pi worker cluster.", no_args_is_help=True)

@app.command(name="deploy-hotfix")
def deploy_hotfix(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name."),
) -> None:
    """
    Safe Cluster Deployment: Builds on Hub (cocli5x1), pushes to registry, and spokes pull.
    """
    effective_campaign = campaign or os.getenv("CAMPAIGN_NAME") or get_campaign()
    if not effective_campaign:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    setup_file_logging("cluster_deploy")
    service = ClusterService(effective_campaign)
    
    console.print(f"[bold cyan]Starting SAFE Cluster Deployment for: {effective_campaign}[/bold cyan]")
    console.print(f"Registry Hub: [yellow]{service.registry_host}[/yellow]")
    
    async def run_deploy() -> None:
        results = await service.deploy_hotfix_safe()
        
        console.print("\n[bold]Deployment Results:[/bold]")
        for host, success in results.items():
            status = "[green]SUCCESS[/green]" if success else "[red]FAILED[/red]"
            console.print(f"  {host:20}: {status}")

    asyncio.run(run_deploy())
    console.print("\n[bold green]Deployment process complete.[/bold green]")

@app.command(name="sync-audit")
def sync_audit(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name."),
) -> None:
    """
    Pulls results from all cluster nodes and runs a quality audit (The 'Watchdog' loop).
    """
    effective_campaign = campaign or os.getenv("CAMPAIGN_NAME") or get_campaign()
    if not effective_campaign:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    service = ClusterService(effective_campaign)
    asyncio.run(service.sync_and_audit())

@app.command(name="gossip-audit")
def gossip_audit(
    target: Optional[str] = typer.Option(None, "--target", "-t", help="Optional IP to send a test datagram to."),
) -> None:
    """
    Diagnostic tool for the cluster Gossip Bridge.
    Checks for received markers and optionally sends a test ping.
    """
    from ..utils.gossip_audit import audit_gossip, send_test_gossip
    
    if target:
        send_test_gossip(target)
    else:
        # Note: audit_gossip has a hardcoded 30s listen if port is free
        audit_gossip()

@app.command(name="push-data")
def push_data(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name."),
    delete: bool = typer.Option(False, "--delete", help="Delete remote files not present locally."),
) -> None:
    """
    Propagates local campaign data to all cluster nodes.
    """
    effective_campaign = campaign or os.getenv("CAMPAIGN_NAME") or get_campaign()
    if not effective_campaign:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    service = ClusterService(effective_campaign)
    asyncio.run(service.push_data(delete=delete))

@app.command(name="status")
def status(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name."),
) -> None:
    """
    Checks health and container status of all nodes in the cluster.
    """
    effective_campaign = campaign or os.getenv("CAMPAIGN_NAME") or get_campaign()
    if not effective_campaign:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    service = ClusterService(effective_campaign)
    nodes = service.get_nodes()
    
    table = Table(title=f"Cluster Status: {effective_campaign}")
    table.add_column("Hostname", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Uptime")
    table.add_column("Details")

    async def check_all() -> None:
        for node in nodes:
            # We use a simple uptime check as a proxy for 'online'
            res = await service.run_remote_command(node, "uptime")
            if "load average" in res:
                table.add_row(node.hostname, "[green]ONLINE[/green]", res.split("up")[1].split(",")[0].strip(), "Ready")
            else:
                table.add_row(node.hostname, "[red]OFFLINE[/red]", "N/A", res.strip()[:30])

    asyncio.run(check_all())
    console.print(table)

if __name__ == "__main__":
    app()
