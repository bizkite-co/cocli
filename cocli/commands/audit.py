import typer
from typing import Optional, Any, List
from pathlib import Path

from rich.console import Console

app = typer.Typer(help="Auditing tools for the cocli system structure and integrity.", no_args_is_help=True)
console = Console()

def dump_cli_tree(command: Any, out: Any, indent: int = 0) -> None:
    name = command.name or "cocli"
    help_text = f" - {command.help.splitlines()[0]}" if command.help else ""
    out.write(" " * indent + f"{name}{help_text}\n")
    
    for param in command.params:
        if getattr(param, "hidden", False):
            continue
        # Typer adds these by default
        if param.name in ["install_completion", "show_completion"]:
            continue
            
        param_name = "/".join(param.opts) if param.opts else param.name
        param_type = f" ({param.type.name})" if hasattr(param.type, 'name') else ""
        required = " [required]" if param.required else ""
        out.write(" " * (indent + 4) + f"{param_name}{param_type}{required}\n")

    if hasattr(command, 'commands'):
        for sub_name, sub_command in sorted(command.commands.items()):
            dump_cli_tree(sub_command, out, indent + 4)

@app.command(name="cli")
def audit_cli(
    ctx: typer.Context,
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path.")
) -> None:
    """
    Dumps the CLI command hierarchy.
    """
    from typer.main import get_command
    from io import StringIO
    
    # Late import main_app to avoid circular dependency
    from ..main import app as main_app
    
    click_command = get_command(main_app)
    
    out = StringIO()
    dump_cli_tree(click_command, out)
    
    report = out.getvalue()
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
        console.print(f"[green]CLI structure dumped to {output}[/green]")
    else:
        console.print(report)

@app.command(name="fs")
def audit_fs(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Specific campaign to audit."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path.")
) -> None:
    """
    Audits the filesystem for OMAP compliance and Screaming Architecture.
    """
    from ..core.audit.fs_auditor import FsAuditor, AuditNode, AuditStatus, dump_audit_tree
    from ..core.paths import paths
    from io import StringIO
    
    auditor = FsAuditor()
    
    # 1. Audit Root (top level components)
    root_node = AuditNode(name="data_root", path=paths.root, is_dir=True, status=AuditStatus.VALID)
    root_node.children.append(auditor.audit_campaigns(campaign))
    root_node.children.append(auditor.audit_queues())
    
    # Add indexes and companies
    indexes_root = paths.root / "indexes"
    idx_node = AuditNode(
        name="indexes", path=indexes_root, is_dir=True,
        status=AuditStatus.VALID if indexes_root.exists() else AuditStatus.MISSING
    )
    if indexes_root.exists():
        for sub in ["scraped_areas", "scraped-tiles", "domains"]:
            p = indexes_root / sub
            idx_node.children.append(AuditNode(
                name=sub, path=p, is_dir=True,
                status=AuditStatus.VALID if p.exists() else AuditStatus.MISSING
            ))
    root_node.children.append(idx_node)
    
    root_node.children.append(AuditNode(
        name="companies", path=paths.root / "companies", is_dir=True,
        status=AuditStatus.VALID if (paths.root / "companies").exists() else AuditStatus.MISSING
    ))
    
    tree = dump_audit_tree(root_node)
    
    if output:
        # For file output, we'll use a plain text version
        out = StringIO()
        file_console = Console(file=out, force_terminal=False, color_system=None)
        file_console.print(tree)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(out.getvalue(), encoding="utf-8")
        console.print(f"[green]Filesystem audit dumped to {output}[/green]")
    else:
        console.print(tree)

@app.command(name="rollout")
def audit_rollout(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name."),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Specific batch to audit. If omitted, audits all active batches."),
    cluster: bool = typer.Option(True, "--cluster/--no-cluster", help="Pull latest results directly from cluster nodes via rsync."),
) -> None:
    """
    Automated diagnostic for active rollout batches across the cluster.
    """
    from ..core.config import get_campaign
    from ..core.paths import paths
    from ..core.sharding import get_geo_shard, get_grid_tile_id
    from ..core.text_utils import slugify
    from ..models.campaigns.mission import MissionTask
    from ..services.cluster_service import ClusterService
    from rich.table import Table
    from datetime import datetime, UTC, timedelta
    import json
    import subprocess
    import asyncio

    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        return

    # 1. Direct Cluster Pull
    if cluster:
        service = ClusterService(campaign_name)
        asyncio.run(service.pull_scraped_tiles())

    # 2. Locate Batches
    discovery_gen = paths.campaign(campaign_name).queue("discovery-gen")
    batches_dir = discovery_gen.pending / "batches"
    
    if name:
        batch_files = [batches_dir / f"{name}.usv"]
    else:
        # Automatically find active-looking batches (rollout_*, canary_*)
        batch_files = sorted(list(batches_dir.glob("canary_*.usv")) + list(batches_dir.glob("rollout_*.usv")))

    if not batch_files:
        console.print(f"[yellow]No active batches found in {batches_dir}[/yellow]")
        return

    results_dir = paths.campaign(campaign_name).queue("gm-list").completed / "results"
    witness_dir = paths.root / "indexes" / "scraped-tiles"
    pending_queue_dir = paths.campaign(campaign_name).queue("gm-list").pending
    
    now = datetime.now(UTC)
    threshold = now - timedelta(hours=48)

    for batch_file in batch_files:
        if not batch_file.exists():
            continue
            
        console.print(f"\n[bold cyan]Auditing Batch: {batch_file.name}[/bold cyan]")
        
        tasks: List[MissionTask] = []
        with open(batch_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        tasks.append(MissionTask.from_usv(line))
                    except Exception:
                        continue

        if not tasks:
            continue

        done = 0
        stale = 0
        active = 0
        pending = 0

        for task in tasks:
            lat_shard = get_geo_shard(float(task.latitude))
            grid_id = get_grid_tile_id(float(task.latitude), float(task.longitude))
            lat_tile, lon_tile = grid_id.split("_")
            phrase_slug = slugify(task.search_phrase)
            
            receipt_file = results_dir / lat_shard / lat_tile / lon_tile / f"{phrase_slug}.json"
            witness_usv = witness_dir / lat_tile / lon_tile / f"{phrase_slug}.usv"
            witness_csv = witness_dir / lat_tile / lon_tile / f"{phrase_slug}.csv"
            
            task_sub_path = f"{lat_shard}/{lat_tile}/{lon_tile}/{phrase_slug}.usv"
            lease_file = pending_queue_dir / task_sub_path / "lease.json"
            
            is_done = False
            comp_at = None
            
            if witness_usv.exists() or witness_csv.exists():
                is_done = True
            elif receipt_file.exists():
                is_done = True
                try:
                    with open(receipt_file, "r") as f:
                        data = json.load(f)
                        comp_at_str = data.get("completed_at")
                        if comp_at_str:
                            comp_at = datetime.fromisoformat(comp_at_str.replace("Z", "+00:00"))
                except Exception:
                    pass

            if is_done:
                if comp_at and comp_at > threshold:
                    done += 1
                else:
                    stale += 1
            elif lease_file.exists():
                active += 1
            else:
                pending += 1

        table = Table(title=f"Results: {batch_file.name}")
        table.add_column("Status", justify="center")
        table.add_column("Count", justify="right")
        table.add_column("Description")
        table.add_row("[bold green]DONE[/]", str(done), "Recently completed")
        table.add_row("[blue]STALE[/]", str(stale), "Indexed/Witnessed (Synced)")
        table.add_row("[yellow]ACTIVE[/]", str(active), "Being scraped")
        table.add_row("[white]PENDING[/]", str(pending), "Waiting in queue")
        console.print(table)

    # 4. Remote Health Check
    hub = "cocli5x1.pi"
    console.print(f"\n[bold]Cluster Hub ({hub}) Health Check:[/bold]")
    log_cmd = "docker logs --tail 100 cocli-supervisor 2>&1 | grep -i 'error' | head -n 5"
    try:
        res = subprocess.run(["ssh", f"mstouffer@{hub}", log_cmd], capture_output=True, text=True)
        if res.stdout:
            console.print("[red]Recent Hub Errors found:[/red]")
            console.print(res.stdout)
        else:
            console.print("[green]No recent errors in Hub logs.[/green]")
    except Exception as e:
        console.print(f"[yellow]Could not check Hub logs: {e}[/yellow]")

@app.command(name="tui")
def audit_tui(
    output: Optional[Path] = typer.Option(
        Path("docs/tui/screen/actual_tree.txt"), "--output", "-o", help="Output file path."
    )
) -> None:
    """
    Dumps the TUI widget hierarchy.
    """
    # This just wraps the existing functionality
    # But cocli tui --dump-tree already does this.
    console.print(f"To dump TUI tree, use: [bold]cocli tui --dump-tree {output}[/bold]")
