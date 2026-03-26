import typer
from typing import Optional, Any, List
from pathlib import Path

from rich.console import Console

app = typer.Typer(
    help="Auditing tools for the cocli system structure and integrity.",
    no_args_is_help=True,
)
queue_app = typer.Typer(help="Audit specific queues.")
app.add_typer(queue_app, name="queue")
console = Console()


@queue_app.command(name="gm-list")
def audit_queue_gm_list(
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name."
    ),
) -> None:
    """
    Run full end-to-end audit for the gm-list queue (compile, compact, report).
    """
    from ..core.auditors.audit_workflow import DataAuditWorkflow
    from ..core.config import get_campaign

    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    workflow = DataAuditWorkflow(campaign=campaign_name, queue="gm-list")
    workflow.start()

    if workflow.state == "completed":
        console.print("[green]Audit completed successfully.[/green]")
    else:
        console.print(f"[red]Audit failed in state: {workflow.state}[/red]")
        raise typer.Exit(1)


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
        param_type = f" ({param.type.name})" if hasattr(param.type, "name") else ""
        required = " [required]" if param.required else ""
        out.write(" " * (indent + 4) + f"{param_name}{param_type}{required}\n")

    if hasattr(command, "commands"):
        for sub_name, sub_command in sorted(command.commands.items()):
            dump_cli_tree(sub_command, out, indent + 4)


@app.command(name="cli")
def audit_cli(
    ctx: typer.Context,
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file path."
    ),
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
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Specific campaign to audit."
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file path."
    ),
    gen_cleanup: bool = typer.Option(
        False,
        "--gen-cleanup",
        help="Generate a distributed cleanup report for orphans.",
    ),
    skip_companies: bool = typer.Option(
        True,
        "--skip-companies/--no-skip-companies",
        help="Skip the massive companies directory for speed.",
    ),
) -> None:
    """
    Audits the filesystem for OMAP compliance and Screaming Architecture.
    """
    from ..core.audit.fs_auditor import FsAuditor, dump_audit_tree
    from io import StringIO
    from datetime import datetime

    auditor = FsAuditor()

    # Perform full audit using schema source of truth
    root_node = auditor.audit_full(
        campaign_name=campaign, skip_companies=skip_companies
    )

    if gen_cleanup:
        orphans = auditor.get_orphans(root_node)
        if not orphans:
            console.print("[green]No orphans found. Nothing to clean.[/green]")
        else:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = Path(".logs") / f"orphan_cleanup_{ts}.txt"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            auditor.generate_removal_report(orphans, report_path)

            console.print(
                f"[bold yellow]Cleanup report generated:[/bold yellow] [cyan]{report_path}[/cyan]"
            )
            console.print(f"[yellow]Found {len(orphans)} orphans.[/yellow]")
            console.print(
                "\n[bold]To execute distributed removal (S3 + Cluster + Local):[/bold]"
            )
            console.print(
                f"  python scripts/execute_cleanup.py --report {report_path} --campaign {campaign or 'roadmap'}"
            )

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
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name."
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="Specific batch to audit. If omitted, audits all active batches.",
    ),
    cluster: bool = typer.Option(
        True,
        "--cluster/--no-cluster",
        help="Pull latest results directly from cluster nodes via rsync.",
    ),
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
        batch_files = sorted(
            list(batches_dir.glob("canary_*.usv"))
            + list(batches_dir.glob("rollout_*.usv"))
        )

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

            receipt_file = (
                results_dir / lat_shard / lat_tile / lon_tile / f"{phrase_slug}.json"
            )
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
                            comp_at = datetime.fromisoformat(
                                comp_at_str.replace("Z", "+00:00")
                            )
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
    log_cmd = (
        "docker logs --tail 100 cocli-supervisor 2>&1 | grep -i 'error' | head -n 5"
    )
    try:
        res = subprocess.run(
            ["ssh", f"mstouffer@{hub}", log_cmd], capture_output=True, text=True
        )
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
        Path("docs/tui/screen/actual_tree.txt"),
        "--output",
        "-o",
        help="Output file path.",
    ),
) -> None:
    """
    Dumps the TUI widget hierarchy.
    """
    # This just wraps the existing functionality
    # But cocli tui --dump-tree already does this.
    console.print(f"To dump TUI tree, use: [bold]cocli tui --dump-tree {output}[/bold]")


@app.command(name="schemas")
def audit_schemas(
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign to audit. Defaults to all."
    ),
    fix: bool = typer.Option(
        False,
        "--fix",
        help="Auto-fix stale schemas by regenerating datapackage.json files.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview changes without applying (used with --fix)."
    ),
) -> None:
    """
    Audit datapackage.json files for schema compliance.

    Checks:
    - datapackage.json files have cocli:schema_hash
    - Schema hashes match the schema_ledger.json
    - No schema drift between model and file

    Examples:
        cocli audit schemas                          # Scan all campaigns
        cocli audit schemas --campaign roadmap       # Scan specific campaign
        cocli audit schemas --fix                    # Auto-fix stale schemas
        cocli audit schemas --fix --dry-run         # Preview fixes
    """
    import json
    from rich.table import Table

    # Import all models that implement SchemaGenerator
    from cocli.models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem
    from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
    from cocli.models.campaigns.queues.to_call import ToCallTask

    SCHEMA_MODELS = [
        GoogleMapsListItem,
        GoogleMapsProspect,
        ToCallTask,
    ]

    # Find all datapackage.json files
    root = Path.cwd()
    console.print("[bold]Scanning for datapackage.json files...[/bold]\n")

    issues_found = []
    files_checked = 0

    for dp_file in root.rglob("datapackage.json"):
        files_checked += 1

        try:
            with open(dp_file, "r") as f:
                dp = json.load(f)

            resource_name = dp.get("name", dp_file.parent.name)
            existing_hash = dp.get("cocli:schema_hash")

            # Check for missing hash (old schema)
            if existing_hash is None:
                issues_found.append(
                    {
                        "file": str(dp_file.relative_to(root)),
                        "issue": "MISSING_SCHEMA_HASH",
                        "details": "Old datapackage.json without schema_hash",
                    }
                )
                continue

            # Check against ledger
            ledger_path = root / "schema_ledger.json"
            if ledger_path.exists():
                with open(ledger_path, "r") as f:
                    ledger = json.load(f)

                if resource_name in ledger:
                    ledger_hash = ledger[resource_name].get("current_hash", "")
                    if ledger_hash and ledger_hash != existing_hash:
                        issues_found.append(
                            {
                                "file": str(dp_file.relative_to(root)),
                                "issue": "HASH_MISMATCH",
                                "details": f"File: {existing_hash[:8]}, Ledger: {ledger_hash[:8]}",
                            }
                        )

        except Exception as e:
            issues_found.append(
                {
                    "file": str(dp_file.relative_to(root)),
                    "issue": "READ_ERROR",
                    "details": str(e),
                }
            )

    # Display results
    console.print(f"Checked {files_checked} datapackage.json files.\n")

    if not issues_found:
        console.print("[green]✓ All schemas are compliant![/green]")
        return

    # Show issues
    table = Table(title="Schema Issues Found")
    table.add_column("File", style="cyan")
    table.add_column("Issue", style="red")
    table.add_column("Details")

    for issue in issues_found:
        table.add_row(
            issue["file"][:50] + "..." if len(issue["file"]) > 50 else issue["file"],
            issue["issue"],
            issue["details"],
        )

    console.print(table)

    # Fix if requested
    if fix and issues_found:
        if dry_run:
            console.print(
                f"\n[yellow]--dry-run: Would fix {len(issues_found)} issues (preview only).[/yellow]"
            )
        else:
            console.print(f"\n[bold]Fixing {len(issues_found)} stale schemas...[/bold]")

            fixed_count = 0
            for issue in issues_found:
                if issue["issue"] in ["MISSING_SCHEMA_HASH", "HASH_MISMATCH"]:
                    dp_file = root / issue["file"]

                    # Try to find the right model for this datapackage
                    # For now, try common models
                    for model in SCHEMA_MODELS:
                        try:
                            model.save_datapackage(  # type: ignore[attr-defined]
                                dp_file.parent,
                                dp_file.parent.name,
                                "*.usv",
                                force=True,
                            )
                            fixed_count += 1
                            console.print(f"  [green]Fixed:[/green] {issue['file']}")
                            break
                        except Exception:
                            continue
                    else:
                        console.print(
                            f"  [red]Could not fix:[/red] {issue['file']} - No matching model"
                        )

            console.print(f"\n[green]Fixed {fixed_count} schemas.[/green]")


@app.command(name="gm-list-html")
def audit_gm_list_html(
    campaign: str = typer.Option("roadmap", "--campaign", "-c", help="Campaign name"),
    limit: int = typer.Option(
        20, "--limit", "-n", help="Number of random HTML files to audit"
    ),
    output: str = typer.Option(
        "gm_list_audit", "--output", "-o", help="Output file name"
    ),
) -> None:
    """
    Audit gm-list HTML files to extract and verify rating/review data.

    Uses the same extractors as the real scraping process to verify
    data quality from raw HTML files.

    Example: cocli audit gm-list-html --campaign roadmap --limit 20
    """
    from cocli.core.auditors.gm_list_auditor import run_html_audit

    result = run_html_audit(campaign, limit=limit, output_name=output)
    console.print(f"[green]Audit results saved to: {result}[/green]")
