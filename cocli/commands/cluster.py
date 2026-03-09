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
    nodes = service.get_nodes()
    
    table = Table(title=f"Cluster Top: {effective_campaign}")
    table.add_column("Node", style="cyan")
    table.add_column("Load")
    table.add_column("Temp")
    table.add_column("MEM Usage")
    table.add_column("PIDs")
    table.add_column("Status")

    async def check_all() -> None:
        for node in nodes:
            # Combined command for speed
            cmd = "uptime && vcgencmd measure_temp && docker stats cocli-supervisor --no-stream --format '{{.MemUsage}} | {{.PIDs}}'"
            res = await service.run_remote_command(node, cmd)
            
            lines = res.strip().split("\n")
            if len(lines) >= 3:
                load = lines[0].split("average:")[1].strip() if "average:" in lines[0] else "N/A"
                temp = lines[1].replace("temp=", "")
                mem_pids = lines[2].split("|")
                mem = mem_pids[0].strip() if len(mem_pids) > 0 else "N/A"
                pids = mem_pids[1].strip() if len(mem_pids) > 1 else "N/A"
                
                table.add_row(node.hostname, load, temp, mem, pids, "[green]OK[/green]")
            else:
                table.add_row(node.hostname, "OFFLINE", "-", "-", "-", "[red]ERR[/red]")

    asyncio.run(check_all())
    console.print(table)

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
            # Stop any container starting with cocli-
            cmd = "docker stop $(docker ps -q --filter name=cocli-) 2>/dev/null || true"
            await service.run_remote_command(node, cmd)
            cmd_rm = "docker rm $(docker ps -a -q --filter name=cocli-) 2>/dev/null || true"
            await service.run_remote_command(node, cmd_rm)

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
