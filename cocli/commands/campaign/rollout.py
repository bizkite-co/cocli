# POLICY: frictionless-data-policy-enforcement
import typer
import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Optional, Annotated, Dict, Any, Tuple
from rich.console import Console
from rich.table import Table

from cocli.core.config import get_campaign
from cocli.core.paths import paths
from cocli.application.operation_service import OperationService

logger = logging.getLogger(__name__)
console = Console()
app = typer.Typer(name="rollout", help="Standardized campaign rollout management.", no_args_is_help=True)


def _get_pi_hostnames() -> Dict[str, str]:
    """Get PI hostnames (Tailscale MagicDNS names)."""
    return {
        "cocli5x0": "cocli5x0.tail87cf32.ts.net",
        "cocli5x1": "cocli5x1.tail87cf32.ts.net",
    }


def _ssh_run(hostname: str, command: str) -> Tuple[int, str]:
    """Run command on remote host via SSH. Returns (exit_code, output)."""
    try:
        result = subprocess.run(
            ["ssh", f"mstouffer@{hostname}", command],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode, result.stdout.strip()
    except subprocess.TimeoutExpired:
        return 1, ""
    except Exception as e:
        return 1, str(e)


def _count_lines_in_dir(path: Path, pattern: str = "*.usv") -> int:
    """Count total lines in all matching files in a directory."""
    count = 0
    if path.exists():
        for file in path.glob(pattern):
            try:
                with open(file, "r") as f:
                    count += sum(1 for _ in f)
            except Exception:
                pass
    return count


def _get_batch_status(campaign_name: str) -> Dict[str, Any]:
    """Get status of all batches for a campaign."""
    dg_queue = paths.campaign(campaign_name).queue("discovery-gen")
    batches_dir = dg_queue.pending / "batches"

    batches = {}
    if batches_dir.exists():
        for batch_file in batches_dir.glob("*.usv"):
            with open(batch_file, "r") as f:
                count = sum(1 for _ in f)
            batches[batch_file.stem] = count

    return batches


def _get_pi_stats(campaign_name: str) -> Dict[str, Dict[str, Any]]:
    """Get scraping stats from each PI."""
    pi_hosts = _get_pi_hostnames()
    stats = {}

    for pi_name, hostname in pi_hosts.items():
        wal_command = (
            f"find ~/repos/data/campaigns/{campaign_name}/indexes/google_maps_prospects/wal "
            "-name '*.usv' 2>/dev/null | xargs wc -l 2>/dev/null | tail -1 | awk '{{print $1}}'"
        )
        active_command = (
            f"find ~/repos/data/campaigns/{campaign_name}/indexes/google_maps_prospects/active "
            "-name '*.usv' 2>/dev/null | xargs wc -l 2>/dev/null | tail -1 | awk '{{print $1}}'"
        )

        rc1, wal_out = _ssh_run(hostname, wal_command)
        rc2, active_out = _ssh_run(hostname, active_command)

        stats[pi_name] = {
            "wal_companies": int(wal_out) if wal_out and wal_out.isdigit() else 0,
            "active_companies": int(active_out) if active_out and active_out.isdigit() else 0,
            "reachable": rc1 == 0 and rc2 == 0,
        }

    return stats

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
    from cocli.core.environment import get_environment
    datagram = ConfigDatagram(
        campaign_name=effective_campaign,
        node_id="*", # Broadcast to all
        config_json=json.dumps(scaling),
        timestamp=str(int(time.time())),
        environment=get_environment().value
    )

    console.print(f"[bold cyan]Broadcasting scaling update for {effective_campaign}...[/bold cyan]")
    
    # We need to start the bridge briefly to send
    bridge.start()
    time.sleep(2) # Give it a moment to discover peers from config
    bridge.broadcast_msg(datagram.to_usv())
    time.sleep(1) # Ensure it's sent
    bridge.stop()
    
    console.print("[bold green]Broadcast complete.[/bold green]")

@app.command(name="push-config")
def push_config(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name."),
) -> None:
    """
    Uploads the local campaign config.toml to S3 (campaigns/{campaign}/config.toml).

    This is the source of truth Fargate tasks pull from at startup, since the
    Fargate image does not bundle the data/ directory and cannot reach the
    Pis' rsync-based config distribution. Run this after any change to
    [prospecting.scaling] (or other config) that Fargate workers need to see.
    """
    effective_campaign = campaign or get_campaign()
    if not effective_campaign:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    from cocli.core.config import load_campaign_config
    from cocli.core.reporting import get_boto3_session, get_data_bucket_name, get_s3_client

    config_path = paths.campaign(effective_campaign).path / "config.toml"
    if not config_path.exists():
        console.print(f"[red]Config not found at {config_path}[/red]")
        raise typer.Exit(1)

    config = load_campaign_config(effective_campaign)
    bucket_name = get_data_bucket_name(config, effective_campaign)
    session = get_boto3_session(config)
    s3 = get_s3_client(session=session)

    s3_key = paths.s3.campaign(effective_campaign).config()
    s3.upload_file(str(config_path), bucket_name, s3_key)
    console.print(f"[bold green]Pushed {config_path} -> s3://{bucket_name}/{s3_key}[/bold green]")


@app.command(name="pull-config")
def pull_config(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name."),
) -> None:
    """
    Downloads campaign config.toml from S3 to local disk (campaigns/{campaign}/config.toml).

    Called by the Fargate container's entrypoint before starting the worker
    orchestrator, since load_campaign_config() only ever reads from local disk
    and the Fargate image doesn't bundle data/. On Fargate this uses the ECS
    Task Role (no profile) via COCLI_RUNNING_IN_FARGATE, matching the pattern
    already used in cocli/core/queue/factory.py.
    """
    import os

    effective_campaign = campaign or get_campaign()
    if not effective_campaign:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    from cocli.core.config import load_campaign_config
    from cocli.core.reporting import get_boto3_session, get_data_bucket_name, get_s3_client

    config = load_campaign_config(effective_campaign)
    bucket_name = os.environ.get("COCLI_S3_BUCKET_NAME") or get_data_bucket_name(config, effective_campaign)

    if os.getenv("COCLI_RUNNING_IN_FARGATE"):
        session = get_boto3_session({})
    else:
        session = get_boto3_session(config)
    s3 = get_s3_client(session=session)

    s3_key = paths.s3.campaign(effective_campaign).config()
    config_path = paths.campaign(effective_campaign).path / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        s3.download_file(bucket_name, s3_key, str(config_path))
        console.print(f"[bold green]Pulled s3://{bucket_name}/{s3_key} -> {config_path}[/bold green]")
    except Exception as e:
        console.print(f"[bold yellow]Warning: Could not pull config from S3 ({e}). Continuing with whatever is on local disk.[/bold yellow]")


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


@app.command(name="status")
def rollout_status(
    campaign_name: Annotated[
        Optional[str], typer.Argument(help="Campaign name")
    ] = None,
) -> None:
    """
    Show current rollout status: batches deployed, and synced results.
    """
    if campaign_name is None:
        campaign_name = get_campaign()

    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    batches = _get_batch_status(campaign_name)

    # Hub local data (synced from S3)
    hub_index_path = (
        paths.campaign(campaign_name).index("google_maps_prospects").path / "active"
    )
    hub_companies = _count_lines_in_dir(hub_index_path)

    # Summary
    console.print(f"\n[bold blue]Rollout Status: {campaign_name}[/bold blue]")
    console.print(f"[dim]{'─' * 70}[/dim]")

    # Batches table
    if batches:
        batch_table = Table(title="Batches Deployed")
        batch_table.add_column("Batch Name", style="cyan")
        batch_table.add_column("Tasks", style="yellow")

        total_tasks = 0
        for batch_name, task_count in sorted(batches.items()):
            batch_table.add_row(batch_name, str(task_count))
            total_tasks += task_count

        console.print(batch_table)
        console.print(f"[bold]Total Deployed: {total_tasks} tasks[/bold]\n")
    else:
        console.print("[yellow]No batches deployed[/yellow]\n")

    # Hub results (deduplicated by place_id)
    console.print("[bold]Results Synced to Hub:[/bold]")
    console.print(f"  Unique Companies: [green]{hub_companies:,}[/green]")
    if batches and total_tasks > 0:
        console.print(f"  Avg per Task: [cyan]{hub_companies / total_tasks:.1f}[/cyan]")

    console.print(f"[dim]{'─' * 70}[/dim]")
    console.print("[dim]Run [bold]cocli campaign rollout sync[/bold] to pull latest results from S3[/dim]\n")


@app.command(name="progress")
def rollout_progress(
    campaign_name: Annotated[
        Optional[str], typer.Argument(help="Campaign name")
    ] = None,
    watch: Annotated[
        bool, typer.Option("--watch", "-w", help="Continuously monitor (updates every 10s)")
    ] = False,
) -> None:
    """
    Show real-time progress of active rollout.
    Reports synced results from hub. Run 'cocli campaign rollout sync' first for latest data.
    """
    if campaign_name is None:
        campaign_name = get_campaign()

    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    import time

    def show_progress() -> None:
        batches = _get_batch_status(campaign_name)
        total_deployed = sum(batches.values())

        hub_index_path = (
            paths.campaign(campaign_name).index("google_maps_prospects").path / "active"
        )
        hub_companies = _count_lines_in_dir(hub_index_path)

        if total_deployed == 0:
            console.print("[yellow]No batches deployed[/yellow]")
            return

        avg_per_task = hub_companies / total_deployed if total_deployed > 0 else 0

        console.print(
            f"[bold]Progress:[/bold] {hub_companies:,} companies from {total_deployed} tasks | "
            f"{avg_per_task:.1f} avg/task"
        )

    if watch:
        while True:
            console.clear()
            show_progress()
            console.print("\n[dim]Syncing every 30 seconds... (press Ctrl+C to stop)[/dim]")
            time.sleep(30)
    else:
        show_progress()


@app.command(name="sync")
def rollout_sync(
    campaign_name: Annotated[
        Optional[str], typer.Argument(help="Campaign name")
    ] = None,
    deduplicate: Annotated[
        bool, typer.Option("--deduplicate", help="Remove duplicate companies across PIs")
    ] = True,
    workers: int = typer.Option(20, help="Number of concurrent download threads"),
    full: bool = typer.Option(False, "--full", help="Perform a full sync (slower)"),
    force: bool = typer.Option(False, "--force", help="Force re-download all files"),
) -> None:
    """
    Sync scraping results from PIs back to hub via S3.
    Deduplicates companies by place_id across all nodes.
    """
    if campaign_name is None:
        campaign_name = get_campaign()

    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    from cocli.core.smart_sync import run_smart_sync
    from cocli.core.config import load_campaign_config
    from cocli.core.reporting import get_data_bucket_name

    console.print(f"[bold cyan]Syncing results for {campaign_name}...[/bold cyan]")

    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    bucket_name = get_data_bucket_name(config, campaign_name)

    # Pull prospects index from S3
    console.print("[yellow]Step 1/3: Pulling prospects index from S3...[/yellow]")
    prefix = f"campaigns/{campaign_name}/indexes/google_maps_prospects/"
    local_base = paths.campaign(campaign_name).index("google_maps_prospects").path
    run_smart_sync(
        "prospects",
        bucket_name,
        prefix,
        local_base,
        campaign_name,
        aws_config,
        workers=workers,
        full=full,
        force=force
    )

    # Count total and deduplicate
    active_path = local_base / "active"
    seen_place_ids: set[str] = set()
    duplicates = 0

    console.print("[yellow]Step 2/3: Deduplicating by place_id...[/yellow]")
    if active_path.exists():
        for usv_file in active_path.glob("*.usv"):
            try:
                with open(usv_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            parts = line.strip().split("\x1f")
                            if len(parts) >= 1:
                                place_id = parts[0]
                                if place_id in seen_place_ids:
                                    duplicates += 1
                                else:
                                    seen_place_ids.add(place_id)
            except Exception as e:
                logger.error(f"Error reading {usv_file}: {e}")

    # Get batch info
    batches = _get_batch_status(campaign_name)
    total_tasks_deployed = sum(batches.values())
    unique_companies = len(seen_place_ids)

    console.print("[yellow]Step 3/3: Reporting results...[/yellow]")
    console.print(f"\n[bold blue]Sync Complete for {campaign_name}[/bold blue]")
    console.print(f"[dim]{'─' * 70}[/dim]")
    console.print(f"  Tasks Deployed: [cyan]{total_tasks_deployed}[/cyan]")
    console.print(f"  Unique Companies Found: [green]{unique_companies:,}[/green]")
    if duplicates > 0:
        console.print(f"  Duplicate Entries Across PIs: [yellow]{duplicates:,}[/yellow]")
    if total_tasks_deployed > 0:
        console.print(f"  Avg Companies/Task: [cyan]{unique_companies / total_tasks_deployed:.1f}[/cyan]")
    console.print(f"[dim]{'─' * 70}[/dim]\n")


@app.command(name="report")
def rollout_report(
    campaign_name: Annotated[
        Optional[str], typer.Argument(help="Campaign name")
    ] = None,
) -> None:
    """
    Detailed audit report: batches, coverage, and synced results.
    """
    if campaign_name is None:
        campaign_name = get_campaign()

    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    batches = _get_batch_status(campaign_name)

    hub_index_path = (
        paths.campaign(campaign_name).index("google_maps_prospects").path / "active"
    )
    hub_companies = _count_lines_in_dir(hub_index_path)

    total_deployed = sum(batches.values())

    console.print(f"\n[bold blue]Rollout Report: {campaign_name}[/bold blue]")
    console.print(f"[dim]{'─' * 70}[/dim]")

    console.print("\n[bold]Deployment Coverage:[/bold]")
    console.print(f"  Batches: {len(batches)}")
    for batch_name, task_count in sorted(batches.items()):
        console.print(f"    {batch_name}: {task_count} tasks")
    console.print(f"  Total Deployed: {total_deployed} tasks")

    console.print("\n[bold]Results (Synced & Deduplicated):[/bold]")
    console.print(f"  Unique Companies: {hub_companies:,}")
    if total_deployed > 0:
        console.print(f"  Avg per Task: {hub_companies / total_deployed:.1f}")

    coverage = (hub_companies / (total_deployed * 10)) * 100 if total_deployed > 0 else 0
    console.print(f"  Coverage Estimate: {coverage:.0f}%")

    console.print("\n[dim]Last synced: Run [bold]cocli campaign rollout sync[/bold] to update[/dim]")
    console.print(f"[dim]{'─' * 70}[/dim]\n")


if __name__ == "__main__":
    app()
