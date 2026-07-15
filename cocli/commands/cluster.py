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

@app.command(name="gossip-audit")
def gossip_audit(
    target: Optional[str] = typer.Option(None, "--target", "-t", help="Optional IP to send a test datagram to."),
    timeout: float = typer.Option(60.0, "--timeout", help="How many seconds to listen for live gossip."),
) -> None:
    """
    Diagnostic tool for the cluster Gossip Bridge.
    Checks for received markers and optionally sends a test ping.
    """
    from ..utils.gossip_audit import audit_gossip, send_test_gossip
    
    if target:
        send_test_gossip(target)
    else:
        audit_gossip(timeout_seconds=timeout)

@app.command(name="top")
def top(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name."),
) -> None:
    """
    Real-time performance monitor for the cluster (CPU, Temp, Workers).
    """
    effective_campaign = campaign or os.getenv("CAMPAIGN_NAME") or get_campaign()
    if not effective_campaign:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    service = ClusterService(effective_campaign)
    
    table = Table(title=f"Cluster Top: {effective_campaign}")
    table.add_column("Node", style="cyan")
    table.add_column("Load")
    table.add_column("Temp")
    table.add_column("MEM Usage")
    table.add_column("PIDs")
    table.add_column("Status")

    async def check_all() -> None:
        stats = await service.get_top_stats()
        for stat in stats:
            if stat["status"] == "OK":
                table.add_row(stat["node"], stat["load"], stat["temp"], stat["mem"], stat["pids"], "[green]OK[/green]")
            else:
                table.add_row(stat["node"], "OFFLINE", "-", "-", "-", "[red]ERR[/red]")

    asyncio.run(check_all())
    console.print(table)

@app.command(name="sync-clocks")
def sync_clocks(
    authoritative_node: str = typer.Option("cocli5x1", "--source", help="Node to use as the time authority."),
) -> None:
    """
    Synchronizes clocks across the cluster using the Hub as the authority.
    """
    from ..services.cluster_service import ClusterService
    import subprocess
    
    # 1. Get current time from authority
    try:
        res = subprocess.run(["ssh", f"mstouffer@{authoritative_node}", "date -u +'%Y-%m-%d %H:%M:%S'"], capture_output=True, text=True, check=True)
        auth_time = res.stdout.strip()
        console.print(f"[cyan]Authority ({authoritative_node}) time: {auth_time} UTC[/cyan]")
    except Exception as e:
        console.print(f"[red]Could not get time from authority: {e}[/red]")
        raise typer.Exit(1)

    # NOTE: ClusterService now resolves nodes per-campaign (each campaign's
    # own config.toml [cluster]/[prospecting.scaling], not one shared global
    # list) - so hardcoding "roadmap" here only syncs roadmap's own nodes,
    # not the whole physical cluster. Pass --campaign through if you need to
    # sync a different campaign's nodes.
    service = ClusterService("roadmap")
    nodes = service.get_nodes()
    
    async def sync_all() -> None:
        for node in nodes:
            if node.hostname == authoritative_node:
                continue
            console.print(f"  Syncing {node.hostname}...")
        await service.sync_clocks(authoritative_node, auth_time)

    asyncio.run(sync_all())
    console.print("[bold green]Clock synchronization complete.[/bold green]")

@app.command(name="stop")
def stop(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name."),
) -> None:
    """
    Stops all cocli worker containers across all cluster nodes.
    """
    effective_campaign = campaign or os.getenv("CAMPAIGN_NAME") or get_campaign()
    if not effective_campaign:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    service = ClusterService(effective_campaign)
    nodes = service.get_nodes()
    
    console.print(f"[bold red]Stopping all workers for campaign: {effective_campaign}[/bold red]")
    
    async def stop_all() -> None:
        for node in nodes:
            console.print(f"  Stopping workers on {node.hostname}...")
        await service.stop_workers()

    asyncio.run(stop_all())
    console.print("[bold green]Cluster stopped.[/bold green]")

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
    
    table = Table(title=f"Cluster Status: {effective_campaign}")
    table.add_column("Hostname", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Uptime")
    table.add_column("Details")

    async def check_all() -> None:
        nodes_status = await service.get_nodes_status()
        for ns in nodes_status:
            if ns["online"]:
                table.add_row(ns["node"], "[green]ONLINE[/green]", ns["uptime"], ns["details"])
            else:
                table.add_row(ns["node"], "[red]OFFLINE[/red]", ns["uptime"], ns["details"])

    asyncio.run(check_all())
    console.print(table)

@app.command(name="prune")
def prune() -> None:
    """
    Prunes unused Docker objects (containers, images, build cache) across all known cluster nodes.
    """
    from ..core.config import get_all_campaign_dirs
    from ..core.paths import paths

    # ClusterService now resolves nodes per-campaign (each campaign's own
    # [cluster]/[prospecting.scaling]) rather than one shared global list, so
    # "all known cluster nodes" means the union of every campaign's nodes,
    # not a single global lookup.
    validated_nodes = []
    seen_hostnames = set()
    for campaign_dir in get_all_campaign_dirs():
        campaign_name = str(campaign_dir.relative_to(paths.campaigns))
        service = ClusterService(campaign_name)
        for node in service.get_nodes():
            if node.hostname not in seen_hostnames:
                seen_hostnames.add(node.hostname)
                validated_nodes.append(node)

    if not validated_nodes:
        console.print("[yellow]No cluster nodes found across any campaign.[/yellow]")
        raise typer.Exit(0)
    # run_remote_command is stateless w.r.t. which campaign built it - reuse
    # whichever ClusterService instance we last constructed above.

    table = Table(title="Cluster Prune Results (All Nodes)")
    table.add_column("Node", style="cyan")
    table.add_column("Status")
    table.add_column("Reclaimed Space", justify="right")

    async def prune_all() -> None:
        for node in validated_nodes:
            console.print(f"  Pruning [cyan]{node.hostname}[/cyan]...")
        prune_results = await service.prune_nodes(validated_nodes)
        for pr in prune_results:
            status = "[green]SUCCESS[/green]" if pr["success"] else "[red]FAILED[/red]"
            table.add_row(pr["node"], status, pr["reclaimed"])

    asyncio.run(prune_all())
    console.print()
    console.print(table)

if __name__ == "__main__":
    app()
