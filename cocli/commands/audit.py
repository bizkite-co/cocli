import re
import typer
from typing import Optional, Any, List
from pathlib import Path

from rich.console import Console
import duckdb
from ..core.paths import paths
from rich.table import Table
from rich.prompt import Prompt
from rich.markup import escape
app = typer.Typer(
    help="Auditing tools for the cocli system structure and integrity.",
    no_args_is_help=True,
)
queue_app = typer.Typer(help="Audit specific queues.", no_args_is_help=True)
app.add_typer(queue_app, name="queue")
console = Console()


def _run_async(coro: Any) -> Any:
    """Run a coroutine from a sync context, avoiding event-loop conflicts."""
    import asyncio
    import threading
    result: list[Any] = []
    exc: list[Exception] = []
    def _target() -> None:
        try:
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            result.append(new_loop.run_until_complete(coro))
            new_loop.close()
        except Exception as e:
            exc.append(e)
    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join()
    if exc:
        raise exc[0]
    return result[0] if result else None


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

@app.command(name="scrape")
def audit_scrape(
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name (defaults to current)."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show sample of pending tiles."),
    threshold: Optional[int] = typer.Option(
        None, "--threshold", help="Exit with error if pending tiles exceed this number."
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Write full JSON report to the given file."
    ),
    include_details: bool = typer.Option(
        False, "--details", help="Also report counts for the gm-details queue."
    ),
    no_duckdb: bool = typer.Option(
        False, "--no-duckdb", help="Force filesystem scan instead of DuckDB.") ,
    summary_only: bool = typer.Option(
        False, "--summary-only", help="Print only JSON summary without Rich table."
    ),
    cluster_pull: bool = typer.Option(
        True, "--cluster/--no-cluster", help="Pull latest data from cluster nodes before audit."
    ),
) -> None:
    """Audit the whole scrape workflow for a campaign.

    Shows config‑derived parameters, distinct discovery tiles,
    and how many of those tiles have already produced gm‑list results.
    """
    from ..core.config import get_campaign
    from ..services.cluster_service import ClusterService
    from rich.table import Table
    import json
    import asyncio
    import logging

    logger = logging.getLogger(__name__)

    # Resolve campaign and optionally pull fresh data
    campaign_name = campaign or get_campaign() or "roadmap"
    if cluster_pull:
        service = ClusterService(campaign_name)
        console.print("[bold cyan]Pulling latest tiles from cluster…[/bold cyan]")
        asyncio.run(service.pull_scraped_tiles())

    # Load campaign config (search phrases, locations, proximity)
    cfg_path = paths.campaign(campaign_name).config
    import tomli
    cfg = tomli.load(cfg_path.open("rb"))
    phrases = cfg.get("prospecting", {}).get("queries", [])
    locations_cfg = cfg.get("prospecting", {}).get("locations", [])
    # Load target locations from file if defined
    target_locations_path = paths.campaign(campaign_name).config.parent / cfg.get("prospecting", {}).get("target-locations-csv", "")
    if target_locations_path and target_locations_path.exists():
        try:
            with open(target_locations_path, "r", encoding="utf-8") as f:
                locations_file = [line.strip() for line in f if line.strip()]
        except Exception:
            locations_file = []
    else:
        locations_file = []
    # Combine config locations and file locations (avoid duplicates)
    locations = list(set(locations_cfg + locations_file))




    proximity = cfg.get("prospecting", {}).get("proximity", "N/A")

    # Audit queues: count valid and invalid records from completed/ subdirectories
    from cocli.utils import duckdb_utils

    def audit_queue(queue_name: str) -> tuple[int, int]:
        """
        Audit a queue's completed records against its datapackage.json schema.
        Returns (valid_records, invalid_records) counts.
        """
        queue_path = paths.campaign(campaign_name).queue(queue_name)
        completed_dir = queue_path.completed
        if (completed_dir / "results").exists():
            completed_dir = completed_dir / "results"
        datapackage_path = completed_dir / "datapackage.json"

        if not completed_dir.exists():
            logger.warning(f"No completed/ directory for queue {queue_name}")
            return 0, 0

        # Find all .usv files in completed/
        usv_files = list(completed_dir.rglob("*.usv"))
        if not usv_files:
            logger.info(f"No .usv files found in {queue_name}/completed/")
            return 0, 0

        # If no datapackage.json, fall back to file count
        if not datapackage_path.exists():
            logger.info(f"No datapackage.json for {queue_name}; counting .usv files as fallback")
            # Count each .usv file as one "unit" (may be multiple records per file)
            return len(usv_files), 0

        try:
            con = duckdb.connect(database=":memory:")

            # Use a safe table name (replace hyphens with underscores)
            safe_table_name = queue_name.replace("-", "_")

            # Load all .usv files into a single table
            duckdb_utils.load_from_datapackage(con, safe_table_name, datapackage_path)

            # Count total and valid records
            total_res = con.execute(f"SELECT COUNT(*) FROM {safe_table_name}").fetchone()
            total_records = total_res[0] if total_res else 0

            # For now, assume all loaded records are valid (schema validation happens at load time)
            valid_records = total_records
            invalid_records = 0

            con.close()
            return valid_records, invalid_records
        except Exception as e:
            logger.warning(f"Error auditing queue {queue_name}: {e}")
            return 0, 0

    # Audit queues to get total records
    discovery_valid, discovery_invalid = audit_queue("discovery-gen")
    gm_list_valid, gm_list_invalid = audit_queue("gm-list")

    # Count unique completed viewports (tiles) in gm-list
    gm_list_root = paths.campaign(campaign_name).queue("gm-list").completed
    if (gm_list_root / "results").exists():
        gm_list_root = gm_list_root / "results"
    gm_list_tiles_set = set()
    if gm_list_root.exists():
        for usv_file in gm_list_root.rglob("*.usv"):
            parts = usv_file.relative_to(gm_list_root).parts
            if len(parts) >= 3:
                gm_list_tiles_set.add(f"{parts[-3]}/{parts[-2]}")
    gm_list_tiles = len(gm_list_tiles_set)

    # Count unique target viewports (tiles) in discovery-gen completed pool
    dg_root = paths.campaign(campaign_name).queue("discovery-gen").completed
    dg_tiles_set = set()
    if dg_root.exists():
        for usv_file in dg_root.rglob("*.usv"):
            parts = usv_file.relative_to(dg_root).parts
            if len(parts) >= 3:
                dg_tiles_set.add(f"{parts[-3]}/{parts[-2]}")
    staged_tiles = len(dg_tiles_set)

    # Count total campaign tiles in map-tile queue (pending + completed)
    map_tile_queue = paths.campaign(campaign_name).queue("map-tile")
    total_campaign_tiles = 0
    if map_tile_queue.pending.exists():
        total_campaign_tiles = len(list(map_tile_queue.pending.rglob("*.usv"))) + len(list(map_tile_queue.completed.rglob("*.usv")))

    # Optional gm-details stats
    details_tiles = None
    if include_details:
        gm_details_root = paths.campaign(campaign_name).queue("gm-details").completed
        details_set: set[str] = set()
        for receipt in gm_details_root.rglob("*.json"):
            parts = receipt.relative_to(gm_details_root).parts
            if len(parts) >= 3:
                details_set.add(f"{parts[0]}/{parts[1]}")
        details_tiles = len(details_set)

    pending_tiles = staged_tiles - gm_list_tiles

    # Build report dict
    report: dict[str, Any] = {
        "campaign": campaign_name,
        "search_phrases": len(phrases),
        "locations": len(locations),
        "proximity": proximity,
        "total_campaign_tiles": total_campaign_tiles,
        "staged_active_tiles": staged_tiles,
        "completed_scraped_tiles": gm_list_tiles,
        "pending_scraped_tiles": pending_tiles,
        "total_active_scrape_tasks": discovery_valid,
        "valid_business_leads": gm_list_valid,
    }
    if include_details:
        report["gm_details_tiles"] = details_tiles


    # Output
    if summary_only:
        console.print(json.dumps(report, indent=2))
    else:
        table = Table(title="Scrape Pipeline Audit")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        for k, v in report.items():
            table.add_row(k.replace("_", " ").title(), str(v))
        console.print(table)
        if verbose and pending_tiles and not no_duckdb:
            # Pending tiles: those in discovery-gen but not yet in gm-list
            console.print(f"\n[bold]Pending tiles to scrape: {pending_tiles}[/bold]")

    # Write JSON if requested
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        console.print(f"[green]Report written to {output}[/green]")

    # Enforce threshold
    if threshold is not None and pending_tiles > threshold:
        console.print(
            f"[red]Pending tiles ({pending_tiles}) exceed threshold ({threshold}) – exiting with error.[/red]"
        )
        raise SystemExit(1)


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
    console.print(f"To dump TUI tree, use: [bold]cocli tui --dump-tree {output}[/bold]")


_KNOWN_CONTENT_TYPES = ["gm-list", "gm-details", "enrichment"]

# gm-list logs one line per multi-minute scrape cycle (page load + scroll), while
# gm-details/enrichment poll their queue every ~5s when idle. A silent worker is
# "stale" once it's gone quiet for longer than its own normal cadence.
_STALE_THRESHOLD_S = {"gm-list": 600.0, "gm-details": 120.0, "enrichment": 120.0}
_DEFAULT_STALE_THRESHOLD_S = 120.0

_CLUSTER_AUDIT_REMOTE_SCRIPT = r"""
# Stream docker logs to a file on disk rather than into a shell variable -
# on a node under heavy memory pressure, `LOGS=$(docker logs ...)` has to
# materialize the *entire* log history as one in-memory string before any
# grep can run, and that allocation can silently fail/truncate exactly when
# the node is unhealthy (i.e. exactly when this audit matters most). A file
# plus streaming grep/tail never holds more than one line in memory.
LOGFILE=$(mktemp)
docker logs cocli-supervisor > "$LOGFILE" 2>&1
docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' cocli-supervisor 2>/dev/null | grep -E '^CAMPAIGN_NAME=' || true
echo '@@WORKERS@@'
grep -E 'Starting worker:' "$LOGFILE" | tail -30 || true
echo '@@ERRORS@@'
docker logs --since 30m cocli-supervisor 2>&1 | grep -icE 'error|exception|traceback|denied' || true
echo '@@ERROR_PATTERNS@@'
# Normalize variable parts (timestamps, per-company/campaign path segments, long
# IDs/hashes/ARNs) so the same underlying error collapses to one bucket instead
# of flooding the top-N with one line per company/task it happened to hit.
docker logs --since 30m cocli-supervisor 2>&1 \
  | grep -iE 'error|exception|traceback|denied' \
  | sed -E 's/^\[[0-9-]+ [0-9:]+ [+-][0-9]+\] //' \
  | sed -E 's#(companies|campaigns)/[A-Za-z0-9_-]+/#\1/*/#g' \
  | sed -E 's/[A-Za-z0-9+\/]{20,}/<ID>/g' \
  | sort | uniq -c | sort -rn | head -5 || true
echo '@@LASTLOG@@'
tail -1 "$LOGFILE" || true
echo '@@TYPE_ACTIVITY@@'
for t in gm-list gm-details enrichment; do
  echo "$t|||$(grep -i "$t" "$LOGFILE" | tail -1)"
done
echo '@@QUEUES@@'
for q in gm-list gm-details enrichment; do
  for s in pending completed failed; do
    c=$(find ~/repos/data/campaigns/__CAMPAIGN__/queues/$q/$s -type f 2>/dev/null | wc -l)
    echo "$q/$s=$c"
  done
done
rm -f "$LOGFILE"
""".strip()

_WORKER_LINE_RE = re.compile(
    r"Starting worker:\s*(?P<name>\S+)\s*\(type=(?P<content_type>[\w-]+),\s*workers=(?P<count>\d+)\)"
)
_LOG_TS_RE = re.compile(r"\[(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4})\]")


def _parse_cluster_audit_sections(raw: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {
        "HEADER": [], "WORKERS": [], "ERRORS": [], "ERROR_PATTERNS": [], "LASTLOG": [],
        "TYPE_ACTIVITY": [], "QUEUES": [],
    }
    current = "HEADER"
    markers = {
        "@@WORKERS@@": "WORKERS", "@@ERRORS@@": "ERRORS", "@@ERROR_PATTERNS@@": "ERROR_PATTERNS",
        "@@LASTLOG@@": "LASTLOG", "@@TYPE_ACTIVITY@@": "TYPE_ACTIVITY", "@@QUEUES@@": "QUEUES",
    }
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped in markers:
            current = markers[stripped]
            continue
        sections[current].append(line)
    return sections


def _log_line_age_seconds(line: str) -> Optional[float]:
    from datetime import datetime

    ts_match = _LOG_TS_RE.search(line)
    if not ts_match:
        return None
    try:
        last_ts = datetime.strptime(ts_match.group("ts"), "%Y-%m-%d %H:%M:%S %z")
        return (datetime.now(last_ts.tzinfo) - last_ts).total_seconds()
    except ValueError:
        return None


def _node_health_verdict(
    has_campaign: bool,
    last_log_age_s: Optional[float],
    error_count: int,
    stale_content_types: list[str],
) -> str:
    if not has_campaign:
        return "[red]OFFLINE[/red]"
    if last_log_age_s is None or last_log_age_s > 120:
        return "[red]STALE[/red]"
    if stale_content_types:
        return f"[red]STALE ({', '.join(stale_content_types)})[/red]"
    if error_count >= 5:
        return "[yellow]DEGRADED[/yellow]"
    return "[green]OK[/green]"


def _format_age(seconds: float) -> str:
    if seconds < 90:
        return f"{int(seconds)}s ago"
    if seconds < 5400:
        return f"{int(seconds / 60)}m ago"
    return f"{seconds / 3600:.1f}h ago"


@app.command(name="cluster")
def audit_cluster(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name (defaults to current)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show each node's raw heartbeat payload (or, with --live, recent log lines)."),
    live: bool = typer.Option(
        False,
        "--live",
        help="Fall back to live SSH+docker-logs polling instead of the fast S3 heartbeat fan-in. "
        "Slow (opens an SSH connection per Pi) and can't see Fargate - use it to dig into a "
        "specific node's actual logs when the heartbeat-based view looks wrong.",
    ),
) -> None:
    """
    Audit cluster nodes: designation (content_type/workers), queue depths, and a
    health signal (recent errors + staleness). Reads from each node's S3 heartbeat
    by default (fast, includes Fargate); pass --live for the old SSH+docker-logs path.
    """
    from ..core.config import get_campaign

    campaign_name = campaign or get_campaign() or "roadmap"

    if live:
        _audit_cluster_live(campaign_name, verbose)
        return

    _audit_cluster_from_heartbeats(campaign_name, verbose)


def _audit_cluster_from_heartbeats(campaign_name: str, verbose: bool) -> None:
    """Fast path: read node health from each node's S3 heartbeat (status/{host}.json)
    instead of opening an SSH connection per node. Node enumeration comes from
    whichever hostnames have a recent heartbeat, which is what makes Fargate show
    up "for free" - it has no SSH endpoint but does write its own heartbeat.
    """
    import json
    from datetime import datetime, timezone

    from ..core.config import load_campaign_config
    from ..core.reporting import get_boto3_session, get_data_bucket_name, get_s3_client

    config = load_campaign_config(campaign_name)
    bucket_name = get_data_bucket_name(config, campaign_name)
    try:
        s3 = get_s3_client(session=get_boto3_session(config))
        status_prefix = paths.s3.status_root
        nodes: dict[str, dict[str, Any]] = {}
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket_name, Prefix=status_prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if not key.endswith(".json"):
                    continue
                hostname = key[len(status_prefix):-len(".json")]
                # Real worker heartbeats are always a flat leaf file directly under
                # status/ (paths.s3.heartbeat writes status/{hostname}.json). A
                # nested path here (e.g. status/registry/<hash>.json) is something
                # else entirely - observed in production to be stale Docker
                # registry access-log debris, not a node - and would otherwise
                # flood this table with dozens of irrelevant STALE rows.
                if "/" in hostname:
                    continue
                try:
                    body = s3.get_object(Bucket=bucket_name, Key=key)["Body"].read()
                    nodes[hostname] = json.loads(body)
                except Exception:
                    continue
    except Exception as e:
        console.print(f"[red]Error: Could not retrieve cluster status from AWS S3 ({e}).[/red]")
        console.print("[yellow]Please check that your AWS credentials are valid and 1Password is unlocked.[/yellow]")
        raise typer.Exit(1)

    if not nodes:
        console.print(f"[yellow]No heartbeats found under s3://{bucket_name}/{status_prefix}[/yellow]")
        return

    # Queue depths are campaign-wide (S3 is the coordination source of truth for
    # gm-details/enrichment leases, and gm-list mirrors its mission tiles there
    # too) rather than owned by any one node, so compute them once, not per-row.
    queue_depths: dict[str, dict[str, int]] = {}
    for q in _KNOWN_CONTENT_TYPES:
        for status in ("pending", "completed", "failed"):
            prefix = f"campaigns/{campaign_name}/queues/{q}/{status}/"
            count = 0
            for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
                count += page.get("KeyCount", len(page.get("Contents", [])))
            queue_depths.setdefault(q, {})[status] = count

    now = datetime.now(timezone.utc)

    table = Table(title=f"Cluster Node Audit: {campaign_name}")
    table.add_column("Node", style="cyan")
    table.add_column("Designation", style="magenta")
    table.add_column("Errors (30m)", justify="right")
    table.add_column("Last Activity")
    table.add_column("Health")

    def _age(ts_raw: Any) -> Optional[float]:
        """Age in seconds of a heartbeat timestamp, tolerating whatever shape
        older/non-orchestrator heartbeat writers happen to have left in S3:
        naive (no tzinfo) ISO strings, raw epoch numbers, missing/null, etc.
        Any node's malformed timestamp should degrade that node to "unknown
        activity", not crash the whole audit for every other node.
        """
        if ts_raw is None:
            return None
        try:
            if isinstance(ts_raw, (int, float)):
                ts = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
            else:
                ts = datetime.fromisoformat(str(ts_raw))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
        return (now - ts).total_seconds()

    for hostname in sorted(nodes):
        payload = nodes[hostname]
        try:
            designation: dict[str, int] = payload.get("designation") or {}
            last_activity: dict[str, str] = payload.get("last_activity") or {}
            error_count = int(payload.get("error_count_30m", 0))
            last_log_age = _age(payload.get("timestamp"))

            stale_content_types = [
                ct for ct in designation
                if (age := _age(last_activity.get(ct))) is None or age > _STALE_THRESHOLD_S.get(ct, _DEFAULT_STALE_THRESHOLD_S)
            ]

            designation_str = "\n".join(f"{ct}: {n}" for ct, n in sorted(designation.items())) if designation else "-"
            activity_str = _format_age(last_log_age) if last_log_age is not None else "-"
            health = _node_health_verdict(True, last_log_age, error_count, stale_content_types)
        except Exception as e:
            table.add_row(hostname, "-", "-", "-", f"[red]MALFORMED ({e})[/red]")
            continue

        table.add_row(hostname, designation_str, str(error_count), activity_str, health)

    console.print(table)

    queue_table = Table(title=f"Campaign Queue Depths: {campaign_name}")
    queue_table.add_column("Queue", style="cyan")
    queue_table.add_column("Pending", justify="right")
    queue_table.add_column("Completed", justify="right")
    queue_table.add_column("Failed", justify="right")
    for q in _KNOWN_CONTENT_TYPES:
        depths = queue_depths.get(q, {})
        queue_table.add_row(q, str(depths.get("pending", 0)), str(depths.get("completed", 0)), str(depths.get("failed", 0)))
    console.print(queue_table)

    if verbose:
        for hostname in sorted(nodes):
            console.print(f"[dim]{hostname} heartbeat:[/dim] {json.dumps(nodes[hostname])}")


def _audit_cluster_live(campaign_name: str, verbose: bool) -> None:
    """Legacy path: opens a live SSH connection per node and greps `docker logs`.
    Slow and can't see Fargate (no SSH endpoint) - kept as an opt-in `--live`
    fallback for deep debugging a specific node's actual log output.
    """
    from ..services.cluster_service import ClusterService
    import asyncio

    service = ClusterService(campaign_name)
    remote_script = _CLUSTER_AUDIT_REMOTE_SCRIPT.replace("__CAMPAIGN__", campaign_name)

    async def collect_node_info(node: Any) -> dict[str, Any]:
        raw = await service.run_remote_command(node, remote_script)
        sections = _parse_cluster_audit_sections(raw)

        has_campaign = any(line.startswith("CAMPAIGN_NAME=") for line in sections["HEADER"])

        # Dedupe by worker name, keeping the last (most recent) definition, then
        # aggregate active worker counts per content_type.
        latest_by_name: dict[str, tuple[str, int]] = {}
        for line in sections["WORKERS"]:
            m = _WORKER_LINE_RE.search(line)
            if m:
                latest_by_name[m.group("name")] = (m.group("content_type"), int(m.group("count")))
        by_content_type: dict[str, int] = {}
        for content_type, count in latest_by_name.values():
            by_content_type[content_type] = by_content_type.get(content_type, 0) + count

        try:
            error_count = int(sections["ERRORS"][0].strip()) if sections["ERRORS"] else 0
        except ValueError:
            error_count = 0

        error_patterns = [line.strip() for line in sections["ERROR_PATTERNS"] if line.strip()]

        last_log_line = sections["LASTLOG"][0].strip() if sections["LASTLOG"] else ""
        last_log_age = _log_line_age_seconds(last_log_line)

        # Per-content-type last activity, so a busy gm-details worker logging every
        # 5s doesn't mask a silently dead enrichment worker on the same container.
        type_activity: dict[str, Optional[float]] = {}
        for line in sections["TYPE_ACTIVITY"]:
            if "|||" not in line:
                continue
            content_type, _, activity_line = line.partition("|||")
            type_activity[content_type] = _log_line_age_seconds(activity_line)

        stale_content_types = []
        for ct in by_content_type:
            age = type_activity.get(ct)
            if age is None or age > _STALE_THRESHOLD_S.get(ct, _DEFAULT_STALE_THRESHOLD_S):
                stale_content_types.append(ct)

        queue_depths: dict[str, dict[str, int]] = {}
        for line in sections["QUEUES"]:
            if "=" not in line:
                continue
            path, count_str = line.split("=", 1)
            if "/" not in path:
                continue
            queue_name, status = path.split("/", 1)
            try:
                queue_depths.setdefault(queue_name, {})[status] = int(count_str)
            except ValueError:
                continue

        return {
            "host": node.hostname,
            "has_campaign": has_campaign,
            "designation": by_content_type,
            "error_count": error_count,
            "error_patterns": error_patterns,
            "last_log_age": last_log_age,
            "last_log_line": last_log_line,
            "stale_content_types": stale_content_types,
            "queue_depths": queue_depths,
        }

    from ..core.config import load_campaign_config
    from ..core.reporting import get_boto3_session, get_data_bucket_name, get_s3_client
    import json
    from datetime import datetime, timezone

    status_prefix = paths.s3.status_root
    s3_nodes: dict[str, dict[str, Any]] = {}
    try:
        config = load_campaign_config(campaign_name)
        bucket_name = get_data_bucket_name(config, campaign_name)
        s3 = get_s3_client(session=get_boto3_session(config))
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket_name, Prefix=status_prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if not key.endswith(".json"):
                    continue
                hostname = key[len(status_prefix):-len(".json")]
                if "/" in hostname:
                    continue
                try:
                    body = s3.get_object(Bucket=bucket_name, Key=key)["Body"].read()
                    s3_nodes[hostname] = json.loads(body)
                except Exception:
                    continue
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"Failed to fetch S3 heartbeats for live audit: {e}")
        console.print(f"[yellow]Warning: Could not fetch S3 heartbeats ({e}). Only showing SSH-audited nodes.[/yellow]")

    async def gather() -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for n in service.get_nodes():
            info = await collect_node_info(n)
            results.append(info)
        return results

    diagnostics: list[dict[str, Any]] = asyncio.run(gather())

    # Merge non-SSH nodes from S3 heartbeats
    ssh_hosts = {d["host"] for d in diagnostics}
    now = datetime.now(timezone.utc)

    def _age(ts_raw: Any) -> Optional[float]:
        if ts_raw is None:
            return None
        try:
            if isinstance(ts_raw, (int, float)):
                ts = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
            else:
                ts = datetime.fromisoformat(str(ts_raw))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
        return (now - ts).total_seconds()

    for hostname in sorted(s3_nodes):
        if hostname in ssh_hosts:
            continue
        payload = s3_nodes[hostname]
        try:
            designation = payload.get("designation") or {}
            last_activity = payload.get("last_activity") or {}
            error_count = int(payload.get("error_count_30m", 0))
            last_log_age = _age(payload.get("timestamp"))
            stale_content_types = [
                ct for ct in designation
                if (age := _age(last_activity.get(ct))) is None or age > _STALE_THRESHOLD_S.get(ct, _DEFAULT_STALE_THRESHOLD_S)
            ]
        except Exception:
            designation = {}
            error_count = 0
            last_log_age = None
            stale_content_types = []

        diagnostics.append({
            "host": hostname,
            "has_campaign": True,
            "designation": designation,
            "error_count": error_count,
            "error_patterns": [],
            "last_log_age": last_log_age,
            "last_log_line": "",
            "stale_content_types": stale_content_types,
            "queue_depths": {},
        })

    table = Table(title=f"Cluster Node Audit: {campaign_name}")
    table.add_column("Node", style="cyan")
    table.add_column("Designation", style="magenta")
    table.add_column("Queues (pending/done)")
    table.add_column("Errors (30m)", justify="right")
    table.add_column("Last Activity")
    table.add_column("Health")

    for d in diagnostics:
        designation = d["designation"]
        if not designation:
            designation_str = "-"
            relevant_queues = list(d["queue_depths"].keys())
        else:
            designation_str = "\n".join(f"{ct}: {n}" for ct, n in sorted(designation.items()))
            relevant_queues = list(designation.keys())

        queue_lines = []
        for q in relevant_queues:
            if d["queue_depths"]:
                depths = d["queue_depths"].get(q, {})
                queue_lines.append(f"{q}: {depths.get('pending', 0)}p / {depths.get('completed', 0)}d")
        queues_str = "\n".join(queue_lines) if queue_lines else "-"

        error_count = d["error_count"]
        errors_str = str(error_count) if d["has_campaign"] else "-"

        if d["last_log_age"] is not None:
            activity_str = _format_age(d["last_log_age"])
        else:
            activity_str = "-"

        health = _node_health_verdict(d["has_campaign"], d["last_log_age"], error_count, d["stale_content_types"])

        table.add_row(d["host"], designation_str, queues_str, errors_str, activity_str, health)

    console.print(table)

    for d in diagnostics:
        if d["error_count"] > 0 and d["error_patterns"]:
            console.print(f"\n[bold yellow]{d['host']} top error patterns:[/bold yellow]")
            for line in d["error_patterns"]:
                console.print(f"  {escape(line)}")

    if verbose:
        for d in diagnostics:
            if d["last_log_line"]:
                console.print(f"[dim]{d['host']} last log:[/dim] {escape(d['last_log_line'])}")


@app.command(name="enrichment")
def audit_enrichment(
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name (defaults to current)."
    ),
) -> None:
    """
    Audit website enrichment metrics for a campaign: counts of enriched companies,
    and how many successfully resolved contact names (people), phone numbers, emails,
    and social media links, along with lead quality tiering.
    """
    from ..core.config import get_campaign, get_companies_dir
    from ..core.text_utils import parse_frontmatter
    from rich.table import Table
    import yaml

    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print("[bold red]Error:[/bold red] No campaign specified.")
        raise typer.Exit(1)

    companies_dir = get_companies_dir()
    if not companies_dir.exists():
        console.print(f"[bold red]Companies directory not found at: {companies_dir}[/bold red]")
        raise typer.Exit(1)

    total_companies = 0
    total_enriched = 0
    has_contact_name = 0
    has_phone = 0
    has_email = 0
    has_social = 0
    tier_1 = 0
    tier_2 = 0
    tier_3 = 0

    # Walk the directory
    for path in companies_dir.iterdir():
        if not path.is_dir():
            continue
        
        # Check if the company belongs to the campaign
        tags_path = path / "tags.lst"
        if not tags_path.exists():
            continue
        
        try:
            with open(tags_path, "r", encoding="utf-8") as f:
                tags = [line.strip() for line in f if line.strip()]
            if campaign_name not in tags:
                continue
        except Exception:
            continue

        total_companies += 1

        # Check for website enrichment
        website_md_path = path / "enrichments" / "website.md"
        if not website_md_path.exists():
            continue

        try:
            content = website_md_path.read_text(encoding="utf-8")
            fm_str = parse_frontmatter(content)
            if not fm_str:
                continue
            data = yaml.safe_load(fm_str)
            if not data:
                continue

            # We consider it processed/enriched if the file exists and is readable
            total_enriched += 1

            # Check flags
            has_name_val = False
            personnel = data.get("personnel", [])
            if isinstance(personnel, list) and len(personnel) > 0:
                if any(p.get("name") or p.get("first_name") or p.get("last_name") for p in personnel if isinstance(p, dict)):
                    has_name_val = True

            has_phone_val = bool(data.get("phone"))
            has_email_val = bool(data.get("email") or data.get("all_emails"))
            has_social_val = any(bool(data.get(f"{platform}_url")) for platform in ["facebook", "linkedin", "instagram", "twitter", "youtube"])

            if has_name_val:
                has_contact_name += 1
            if has_phone_val:
                has_phone += 1
            if has_email_val:
                has_email += 1
            if has_social_val:
                has_social += 1

            # Quality Tiers
            if has_name_val and (has_email_val or has_phone_val or has_social_val):
                tier_1 += 1
            elif has_email_val or has_phone_val or has_social_val:
                tier_2 += 1
            else:
                tier_3 += 1

        except Exception:
            continue

    # Render Table
    table = Table(title=f"Enrichment Health Audit: {campaign_name}")
    table.add_column("Metric/Segment", style="cyan")
    table.add_column("Count", justify="right", style="magenta")
    table.add_column("Percentage", justify="right", style="green")

    # Add row helper
    def add_metric_row(label: str, count: int, base_count: int) -> None:
        pct = (count / base_count * 100) if base_count > 0 else 0.0
        table.add_row(label, str(count), f"{pct:.1f}%")

    add_metric_row("Total Campaign Companies", total_companies, total_companies)
    add_metric_row("Total Enriched (Processed)", total_enriched, total_companies)
    
    table.add_section()
    # These metrics are out of the processed/enriched ones
    add_metric_row("Has Contact Name (People)", has_contact_name, total_enriched)
    add_metric_row("Has Phone Number", has_phone, total_enriched)
    add_metric_row("Has Email Address", has_email, total_enriched)
    add_metric_row("Has Social Media Link", has_social, total_enriched)

    table.add_section()
    # Lead Quality Tiers
    add_metric_row("Tier 1 Lead (Name + Email/Phone/Social)", tier_1, total_enriched)
    add_metric_row("Tier 2 Lead (No Name, has Contact Point)", tier_2, total_enriched)
    add_metric_row("Tier 3 Lead (No Contact Info / Dead)", tier_3, total_enriched)

    console.print(table)


@app.command(name="enrichment-interactive")
def audit_enrichment_interactive(
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name (defaults to current)."
    ),
) -> None:
    """
    Interactively step through companies that have no contact name (Tiers 2 & 3)
    and open their websites in the browser to inspect and find contacts.
    """
    from ..core.config import get_campaign, get_companies_dir
    from ..core.text_utils import parse_frontmatter
    import yaml
    import webbrowser

    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print("[bold red]Error:[/bold red] No campaign specified.")
        raise typer.Exit(1)

    companies_dir = get_companies_dir()
    if not companies_dir.exists():
        console.print(f"[bold red]Companies directory not found at: {companies_dir}[/bold red]")
        raise typer.Exit(1)

    targets = [] # list of (domain, company_name, slug, has_email, has_phone)
    
    # Walk the directory
    for path in sorted(companies_dir.iterdir(), key=lambda p: p.name):
        if not path.is_dir():
            continue
        
        tags_path = path / "tags.lst"
        if not tags_path.exists():
            continue
        
        try:
            with open(tags_path, "r", encoding="utf-8") as f:
                tags = [line.strip() for line in f if line.strip()]
            if campaign_name not in tags:
                continue
        except Exception:
            continue

        website_md_path = path / "enrichments" / "website.md"
        if not website_md_path.exists():
            domain = None
            name = path.name
            index_md = path / "_index.md"
            if index_md.exists():
                try:
                    fm = parse_frontmatter(index_md.read_text(encoding="utf-8"))
                    if fm:
                        idx_data = yaml.safe_load(fm)
                        if idx_data:
                            domain = idx_data.get("domain")
                            name = idx_data.get("name") or path.name
                except Exception:
                    pass
            if domain:
                targets.append((domain, name, path.name, False, False))
            continue

        try:
            content = website_md_path.read_text(encoding="utf-8")
            fm_str = parse_frontmatter(content)
            if not fm_str:
                continue
            data = yaml.safe_load(fm_str)
            if not data:
                continue

            has_name_val = False
            personnel = data.get("personnel", [])
            if isinstance(personnel, list) and len(personnel) > 0:
                if any(p.get("name") or p.get("first_name") or p.get("last_name") for p in personnel if isinstance(p, dict)):
                    has_name_val = True

            if not has_name_val:
                domain = data.get("url") or data.get("domain") or path.name
                name = data.get("company_name") or data.get("title") or path.name
                has_email = bool(data.get("email") or data.get("all_emails"))
                has_phone = bool(data.get("phone"))
                targets.append((domain, name, path.name, has_email, has_phone))
        except Exception:
            continue

    if not targets:
        console.print("[green]All enriched companies already have contact names! Nothing to inspect.[/green]")
        return

    console.print(f"[bold cyan]Found {len(targets)} companies without contact names.[/bold cyan]")
    
    idx = 0
    while True:
        domain, name, slug, has_email, has_phone = targets[idx]
        console.print(f"\n[bold green][Company {idx + 1}/{len(targets)}][/bold green]")
        console.print(f"  Name:   [bold]{name}[/bold]")
        console.print(f"  Domain: [cyan]{domain}[/cyan]")
        console.print(f"  Slug:   {slug}")
        console.print(f"  Contact status: Email={has_email}, Phone={has_phone}")
        
        console.print("\n[yellow]Options: [o] open in browser, [n] next, [p] previous, [g <num>] go to number, [q] quit[/yellow]")
        choice = typer.prompt("Select option").strip().lower()
        
        if choice == 'o':
            url = f"https://{domain}" if not domain.startswith(("http://", "https://")) else domain
            console.print(f"Opening {url}...")
            webbrowser.open(url)
        elif choice == 'n':
            if idx < len(targets) - 1:
                idx += 1
            else:
                console.print("[red]Already at the last company.[/red]")
        elif choice == 'p':
            if idx > 0:
                idx -= 1
            else:
                console.print("[red]Already at the first company.[/red]")
        elif choice.startswith('g'):
            try:
                num = int(choice.split()[1]) - 1
                if 0 <= num < len(targets):
                    idx = num
                else:
                    console.print(f"[red]Invalid company index (must be 1-{len(targets)}).[/red]")
            except Exception:
                try:
                    num = int(choice[1:]) - 1
                    if 0 <= num < len(targets):
                        idx = num
                    else:
                        console.print("[red]Invalid company index.[/red]")
                except Exception:
                    console.print("[red]Usage: g <number> or g<number>[/red]")
        elif choice == 'q':
            console.print("[green]Exiting interactive audit.[/green]")
            break
        else:
            console.print("[red]Invalid choice.[/red]")


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


@queue_app.command(name="validate")
def audit_validate(
    campaign: str = typer.Argument("roadmap", help="Campaign name"),
    tile: str = typer.Option(
        None, "--tile", help="Grid tile coordinates as lat,lon (e.g. 34.1,-118.4)"
    ),
    phrase: str = typer.Option(
        None, "--phrase", "-p", help="Search phrase to scrape and review"
    ),
    usv_path: Path = typer.Option(
        None,
        "--usv-path",
        help="Path to existing USV file (skip scrape, review offline)",
        exists=False,
    ),
    headed: bool = typer.Option(
        False, "--headed", help="Run scrape in headed mode"
    ),
    limit: int = typer.Option(
        0, "--limit", "-n", help="Max records to review (0 = all)"
    ),
) -> None:
    """
    Human-in-the-loop validation for gm-list results.

    Two modes:
      ONLINE  (--tile + --phrase): scrapes live, saves USV, then reviews.
      OFFLINE (--usv-path):         reviews an existing USV file.

    For each company, walks through fields and prompts for corrections.
    Only corrected fields are saved as GmListReviewedItem entries.

    Examples:
      cocli audit queue validate roadmap --tile 34.1,-118.4 --p "financial-advisor"
      cocli audit queue validate --usv-path data/.../results/3/34.1/-118.4/foo.usv
    """
    import csv
    import sys
    from datetime import datetime, UTC

    from ..core.paths import paths
    from ..core.text_utils import slugify
    from ..models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem
    from ..models.campaigns.indexes.gm_list_audit_log_item import GmListAuditLogItem
    from ..models.campaigns.indexes.gm_list_reviewed_item import GmListReviewedItem
    from ..application.processors.gm_list import GmListProcessor

    if usv_path:
        mode = "offline"
        if not usv_path.exists():
            console.print(f"[red]Error: USV file not found: {usv_path}[/red]")
            raise typer.Exit(1)
        console.print(f"[bold]Offline review:[/bold] [cyan]{usv_path}[/cyan]")
    elif tile and phrase:
        mode = "online"
        try:
            parts = tile.split(",")
            lat = float(parts[0].strip())
            lon = float(parts[1].strip())
        except (ValueError, IndexError):
            console.print("[red]--tile must be lat,lon (e.g. 34.1,-118.4)[/red]")
            raise typer.Exit(1)
        phrase_slug = slugify(phrase)
        console.print(f"[bold]Online review:[/bold] [cyan]{phrase}[/cyan] at [cyan]{tile}[/cyan]")
    else:
        console.print("[red]Provide --tile + --phrase (online) OR --usv-path (offline).[/red]")
        raise typer.Exit(1)

    # Step 1: Scrape (online mode only)
    items = []
    if mode == "online":
        scrape_type = "headless" if not headed else "headed"
        console.print(f"\n[bold yellow]Step 1: Running {scrape_type} scrape...[/bold yellow]")
        from ..models.campaigns.queues.gm_list import ScrapeTask
        from ..core.sharding import get_geo_shard, get_grid_tile_id

        lat_shard = get_geo_shard(lat)
        grid_id = get_grid_tile_id(lat, lon)
        lat_tile_v, lon_tile_v = grid_id.split("_")

        async def run_scrape() -> list[Any]:
            from playwright.async_api import async_playwright
            from ..scrapers.google.gm_scraper.coordinator import ScrapeCoordinator

            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=not headed)
                try:
                    coordinator = ScrapeCoordinator(
                        browser, campaign_name=campaign, debug=False
                    )
                    scraped = []
                    scrape_limit = limit if limit > 0 else 20
                    async for item in coordinator.run(
                        start_lat=lat,
                        start_lon=lon,
                        search_phrases=[phrase],
                        force_refresh=True,
                    ):
                        scraped.append(item)
                        if len(scraped) >= scrape_limit:
                            break
                    return scraped
                finally:
                    await browser.close()

        items = _run_async(run_scrape())

        if not items:
            console.print("[yellow]No items scraped. Skipping review but recording audit log.[/yellow]")
        else:
            task = ScrapeTask(
                latitude=lat,  # type: ignore[arg-type]
                longitude=lon,  # type: ignore[arg-type]
                zoom=15,
                search_phrase=phrase,
                campaign_name=campaign,
                force_refresh=True,
                ack_token=f"validate-{phrase_slug}-{datetime.now(UTC).timestamp()}",
            )
            processor = GmListProcessor(processed_by="audit-validate")
            _run_async(processor.process_results(task, items))
            console.print(f"[green]  Scraped {len(items)} companies. Saved to results/[/green]")

            usv_path = (
                paths.queue(campaign, "gm-list").completed
                / "results"
                / lat_shard
                / lat_tile_v
                / lon_tile_v
                / f"{phrase_slug}.usv"
            )

    # Step 2: Locate / read USV records
    if not usv_path or not usv_path.exists():
        console.print("[red]No USV file available for review.[/red]")
        raise typer.Exit(1)

    field_names = list(GoogleMapsListItem.model_fields.keys())
    excluded = {n for n, f in GoogleMapsListItem.model_fields.items() if f.exclude}
    review_skip = {"place_id", "company_slug"}
    display_fields = [n for n in field_names if n not in excluded and n not in review_skip]

    records = []
    with open(usv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\x1f")
        for row in reader:
            if row:
                while len(row) < len(field_names):
                    row.append("")
                records.append(row[: len(field_names)])

    console.print(f"[dim]  Read {len(records)} records from {usv_path}[/dim]")

    # Step 3: Record audit log entry
    audit_dir = paths.queue(campaign, "gm-list").pending / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    try:
        records_file = str(usv_path.relative_to(paths.queue(campaign, "gm-list").completed))
    except ValueError:
        records_file = str(usv_path.name)

    log_item = GmListAuditLogItem.create(
        tile=str(usv_path.parent),
        search_phrase=phrase or usv_path.stem,
        total_companies=len(items) if mode == "online" else len(records),
        records_file=records_file,
        usv_count=len(records),
        scraper_version="audit-validate",
    )
    audit_log = audit_dir / "gm_list_audit_log.usv"
    with open(audit_log, "a", encoding="utf-8") as f:
        f.write(log_item.to_usv())
    GmListAuditLogItem.append_resource_to_datapackage(
        audit_dir, "gm_list_audit_log", "gm_list_audit_log.usv"
    )
    console.print(f"[green]  Audit log entry saved to {audit_log}[/green]")

    # Step 4: Interactive field-level review
    console.print("\n[bold yellow]Step 4: Field-level review[/bold yellow]")
    console.print("[dim]For each company, review the scraped fields.[/dim]")
    console.print("[dim]    - Press Enter to keep the current value[/dim]")
    console.print("[dim]    - Type a correction to overwrite[/dim]")
    console.print("[dim]    - Type [bold].skip[/bold] to skip this record[/dim]\n")

    # Open Google Maps search in headed Playwright browser for visual comparison
    try:
        usv_str = str(usv_path.resolve())
        parts = usv_str.split("/")
        try:
            ri = next(i for i, p in enumerate(parts) if p == "results")
            ref_lat = parts[ri + 2]
            ref_lon = parts[ri + 3]
            phrase = parts[ri + 4].replace(".usv", "")
        except (StopIteration, IndexError):
            ref_lat = ref_lon = phrase = None  # type: ignore[assignment]

        if ref_lat and ref_lon and phrase:
            search_url = f"https://www.google.com/maps/search/{phrase}/@{ref_lat},{ref_lon},13z"
            console.print(f"[dim]  Opening reference browser: {search_url}[/dim]")

            import threading
            import asyncio

            def _open_ref_browser(url: str) -> None:
                try:
                    async def _run() -> None:
                        from playwright.async_api import async_playwright
                        async with async_playwright() as pw:
                            browser = await pw.chromium.launch(
                                headless=False,
                                args=["--start-maximized"]
                            )
                            context = await browser.new_context(no_viewport=True)
                            page = await context.new_page()
                            await page.goto(url, wait_until="domcontentloaded")
                            while True:
                                await asyncio.sleep(3600)
                    asyncio.run(_run())
                except Exception:
                    pass

            console.print("[dim]  Launching reference browser...[/dim]")
            t = threading.Thread(target=_open_ref_browser, args=(search_url,), daemon=True)
            t.start()
    except Exception:
        pass

    # Load existing corrections
    reviewed_path = audit_dir / "gm_list_reviewed.usv"

    already_reviewed: set[str] = set()
    if reviewed_path.exists():
        with open(reviewed_path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("\x1f")
                if len(parts) >= 1 and parts[0]:
                    already_reviewed.add(parts[0])

    # Ensure datapackage includes all resources
    for model_cls, name, path in [
        (GmListReviewedItem, "gm_list_reviewed", "gm_list_reviewed.usv"),
        (GmListAuditLogItem, "gm_list_audit_log", "gm_list_audit_log.usv"),
    ]:
        model_cls.append_resource_to_datapackage(audit_dir, name, path)  # type: ignore[attr-defined]

    reviewed_count = 0
    skipped_count = 0
    corrected_count = 0

    for idx, record in enumerate(records):
        if limit > 0 and idx >= limit:
            break

        place_id = record[0] if len(record) > 0 else ""

        if place_id and place_id in already_reviewed:
            skipped_count += 1
            continue

        if not sys.stdin.isatty():
            console.print(f"  [{idx + 1}/{len(records)}] {record[2] if len(record) > 2 else '?'} (non-TTY, skipped)")
            continue

        name = record[2] if len(record) > 2 else "?"
        console.print(f"\n[bold cyan]─── [{idx + 1}/{len(records)}] {name} ───[/bold cyan]")
        if place_id:
            console.print(f"[dim]{place_id}[/dim]")

        changes = {}
        skipped_record = False

        for field_name in display_fields:
            fi = field_names.index(field_name)
            if fi >= len(record):
                break
            current_val = record[fi].strip()

            disp = current_val[:60] + "..." if len(current_val) > 60 else current_val
            # Escape brackets so rich doesn't interpret them as style tags (e.g. [purefinancial.com])
            prompt_text = f"  {field_name:<18} \\[{escape(disp)}\\]"
            try:
                corrected = Prompt.ask(prompt_text, default=current_val, show_default=False).strip()
            except TypeError:
                corrected = Prompt.ask(prompt_text, default=current_val).strip()

            if corrected.lower() == ".skip":
                skipped_record = True
                break
            if corrected != current_val:
                changes[field_name] = corrected

        if not skipped_record:
            header_needed = not reviewed_path.exists() or reviewed_path.stat().st_size == 0
            with open(reviewed_path, "a", encoding="utf-8") as f:
                if header_needed and GmListReviewedItem.HEADER:
                    f.write(GmListReviewedItem.get_header())
                if changes:
                    for field_name, val in changes.items():
                        item = GmListReviewedItem(
                            place_id=place_id,
                            field_name=field_name,
                            expected=val,
                        )
                        f.write(item.to_usv())
                    corrected_count += len(changes)
                else:
                    # Mark as reviewed even if no fields changed
                    item = GmListReviewedItem(
                        place_id=place_id,
                        field_name="_reviewed",
                        expected="true",
                    )
                    f.write(item.to_usv())
            
            if place_id:
                already_reviewed.add(place_id)

        reviewed_count += 1

    # Summary
    console.print("\n[bold]─── Validation Summary ───[/bold]")
    table = Table()
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")
    table.add_row("Records in USV", str(len(records)))
    table.add_row("Reviewed interactively", str(reviewed_count))
    table.add_row("Skipped (already done)", str(skipped_count))
    table.add_row("Field corrections", str(corrected_count))
    console.print(table)
    console.print(f"\n[green]Audit log:[/green] {audit_log}")
    if reviewed_path.exists():
        console.print(f"[green]Reviewed:[/green]    {reviewed_path}")
    console.print("[green]Done.[/green]")


@queue_app.command(name="replay", no_args_is_help=True)
def audit_replay(
    campaign: str = typer.Argument("roadmap", help="Campaign name"),
    usv_path: Path = typer.Argument(
        ..., help="Path to a USV results file to apply corrections to", exists=True
    ),
    output: Path = typer.Option(
        None,
        "--output", "-o",
        help="Output path for corrected USV (default: <original>.corrected.usv)",
    ),
    corrections_path: Path = typer.Option(
        None,
        "--corrections",
        help="Path to GmListCorrectionItem USV (default: <campaign>/audit/gm_list_corrections.usv)",
    ),
    reviewed_path_opt: Path = typer.Option(
        None,
        "--reviewed",
        help="Path to GmListReviewedItem USV (default: <campaign>/audit/gm_list_reviewed.usv)",
    ),
) -> None:
    """
    Replay audit corrections onto a USV results file.

    Reads the original USV file, applies all field-level corrections
    from gm_list_corrections.usv and gm_list_reviewed.usv.

    Example:
        cocli audit queue replay roadmap \\
          data/.../results/3/34.1/-118.4/financial-advisor.usv
    """
    from collections import defaultdict
    from ..models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem
    from ..core.paths import paths

    audit_dir = paths.queue(campaign, "gm-list").pending / "audit"

    if not corrections_path:
        corrections_path = audit_dir / "gm_list_corrections.usv"
    if not reviewed_path_opt:
        reviewed_path_opt = audit_dir / "gm_list_reviewed.usv"

    # 1. Load corrections
    field_corrections: dict[str, dict[str, str]] = defaultdict(dict)
    if corrections_path.exists():
        with open(corrections_path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("\x1f")
                if len(parts) >= 4:
                    place_id = parts[0]
                    field_name = parts[1]
                    corrected_val = parts[3]
                    field_corrections[place_id][field_name] = corrected_val
        console.print(f"[dim]  Loaded {sum(len(v) for v in field_corrections.values())} corrections for {len(field_corrections)} place_ids[/dim]")

    # 2. Load reviewed entries (field-level diffs)
    reviewed_overrides: dict[str, dict[str, str]] = defaultdict(dict)
    if reviewed_path_opt.exists():
        with open(reviewed_path_opt, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("\x1f")
                if len(parts) >= 3:
                    place_id = parts[0]
                    field_name = parts[1]
                    expected_val = parts[2]
                    if field_name and expected_val:
                        reviewed_overrides[place_id][field_name] = expected_val
        console.print(f"[dim]  Loaded {sum(len(v) for v in reviewed_overrides.values())} field-level reviewed entries for {len(reviewed_overrides)} place_ids[/dim]")

    # 3. Read & transform USV records
    field_names = list(GoogleMapsListItem.model_fields.keys())
    excluded = {n for n, f in GoogleMapsListItem.model_fields.items() if f.exclude}
    display_names = [n for n in field_names if n not in excluded]

    import csv
    records: list[list[str]] = []
    with open(usv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\x1f")
        for row in reader:
            if row:
                while len(row) < len(field_names):
                    row.append("")
                row = row[: len(field_names)]
                records.append(row)

    applied_count = 0
    reviewed_applied = 0
    for row in records:
        place_id = row[0] if len(row) > 0 else ""
        if not place_id:
            continue

        all_overrides = field_corrections.get(place_id, {}).copy()
        if place_id in reviewed_overrides:
            all_overrides.update(reviewed_overrides[place_id])

        if all_overrides:
            for fi, fn in enumerate(display_names):
                if fn in all_overrides:
                    row[fi] = all_overrides[fn]
                    if fn in field_corrections.get(place_id, {}):
                        applied_count += 1
                    else:
                        reviewed_applied += 1

    # 4. Write corrected output
    output_path = output or usv_path.with_suffix(".corrected.usv")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for row in records:
            f.write("\x1f".join(row) + "\x1e\n")

    console.print(f"[green]  Corrected USV written to: {output_path}[/green]")
    table = Table(title="Replay Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")
    table.add_row("Records in source USV", str(len(records)))
    table.add_row("Field corrections applied", str(applied_count))
    table.add_row("Rating/review overrides", str(reviewed_applied))
    console.print(table)


@queue_app.command(name="export-cases")
def audit_export_cases(
    campaign: str = typer.Argument("roadmap", help="Campaign name"),
    tile: str = typer.Option(
        None, "--tile", help="Grid tile coordinates as lat,lon (e.g. 34.1,-118.4)"
    ),
    phrase: str = typer.Option(
        None, "--phrase", "-p", help="Search phrase"
    ),
) -> None:
    """
    Export field-level corrections as parametrized test cases.

    Reads reviewed corrections from pending/audit/gm_list_reviewed.usv,
    resolves the raw HTML path for each place_id, and writes
    tests/data/maps.google.com/field_extraction_cases.usv.

    Example:
        cocli audit queue export-cases --tile 29.1,-98.4 --phrase financial-advisor
    """
    from ..core.paths import paths

    # Read reviewed corrections
    reviewed_path = paths.queue(campaign, "gm-list").pending / "audit" / "gm_list_reviewed.usv"
    if not reviewed_path.exists():
        console.print("[red]No gm_list_reviewed.usv found. Run audit validate first.[/red]")
        raise typer.Exit(1)

    import csv
    corrections: list[tuple[str, str, str]] = []
    with open(reviewed_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\x1f")
        for row in reader:
            if len(row) >= 3 and row[0].startswith("ChIJ"):
                corrections.append((row[0], row[1], row[2]))

    if not corrections:
        console.print("[yellow]No corrections found in reviewed file.[/yellow]")
        return

    console.print(f"[dim]  Loaded {len(corrections)} corrections[/dim]")

    # Resolve raw HTML paths by searching the raw/gm-list directory
    raw_base = paths.campaign(campaign).path / "raw" / "gm-list"
    if not raw_base.exists():
        console.print(f"[red]Raw HTML directory not found: {raw_base}[/red]")
        raise typer.Exit(1)

    cases: list[tuple[str, str, str, Path]] = []
    missing_html = 0
    for place_id, field, expected in corrections:
        html_path: Path | None = None
        for html_file in raw_base.rglob(f"{place_id}.html"):
            html_path = html_file
            break
        if html_path is None:
            missing_html += 1
            continue
        cases.append((place_id, field, expected, html_path))

    if not cases:
        console.print("[yellow]No cases could be resolved (no matching HTML files).[/yellow]")
        if missing_html:
            console.print(f"[dim]  ({missing_html} corrections had no matching HTML)[/dim]")
        return

    # Copy HTML files into test data directory
    test_data_dir = Path("tests/data/maps.google.com")
    html_dir = test_data_dir / "html"
    html_dir.mkdir(parents=True, exist_ok=True)

    for place_id, field, expected, src_html in cases:
        dst = html_dir / f"{place_id}.html"
        if not dst.exists():
            dst.write_bytes(src_html.read_bytes())

    # Write test cases file (html_path relative to test_data_dir)
    test_cases_path = test_data_dir / "field_extraction_cases.usv"
    HEADER_LINE = "\x1f".join(["place_id", "field", "expected", "html_path"])
    with open(test_cases_path, "w", encoding="utf-8") as f:
        f.write(HEADER_LINE + "\n")
        for place_id, field, expected, _ in cases:
            html_rel = f"html/{place_id}.html"
            f.write("\x1f".join([place_id, field, expected, html_rel]) + "\n")

    console.print(f"[green]  {len(cases)} test cases written to: {test_cases_path}[/green]")
    if missing_html:
        console.print(f"[dim]  ({missing_html} corrections skipped — no matching HTML file)[/dim]")

    # Also update datapackage
    from ..models.campaigns.indexes.gm_list_reviewed_item import GmListReviewedItem
    GmListReviewedItem.append_resource_to_datapackage(
        test_data_dir, "field_extraction_cases", "field_extraction_cases.usv"
    )


@queue_app.command(name="tile-status")
def queue_status(campaign: str = typer.Option("", help="Campaign name")) -> None:
    """
    Audit tile-queue status: pending/processing/completed tiles with lease info.

    Shows tile queue state, processing tiles with lease expiration, and warns
    about expired leases (stuck tiles that will be reclaimed).
    """
    from ..core.queue.factory import get_queue_manager
    from datetime import datetime, UTC
    import json

    campaign_name = campaign or "default"
    tile_queue = get_queue_manager("map-tile", queue_type="tile", campaign_name=campaign_name)

    # Count tiles in each state
    pending_count = 0
    if tile_queue.tiles_dir.exists():
        pending_count = len(list(tile_queue.tiles_dir.glob("*.usv")))

    processing_count = 0
    processing_tiles = []
    expired_count = 0
    if tile_queue.processing_dir.exists():
        for f in tile_queue.processing_dir.glob("*.usv"):
            processing_count += 1
            processing_tiles.append(f)

            # Check lease
            lease_path = tile_queue.processing_dir / f"{f.name}.lease.json"
            if lease_path.exists():
                try:
                    with lease_path.open() as lf:
                        lease = json.load(lf)
                        expires_at = datetime.fromisoformat(lease["expires_at"])
                        if datetime.now(UTC) >= expires_at:
                            expired_count += 1
                except Exception:
                    pass

    completed_count = 0
    if tile_queue.completed_dir.exists():
        completed_count = len(list(tile_queue.completed_dir.glob("*.usv")))

    # Display status table
    console.print(f"\n[bold]Tile Queue Status: {campaign_name}[/bold]\n")

    table = Table(title="State Summary")
    table.add_column("State", style="cyan")
    table.add_column("Count", style="magenta")

    table.add_row("Pending", str(pending_count))
    table.add_row("Processing", str(processing_count))
    table.add_row("Completed", str(completed_count))

    console.print(table)

    # Show details of processing tiles with leases
    if processing_tiles:
        console.print("\n[bold]Processing Tiles:[/bold]")
        for tile_path in sorted(processing_tiles):
            lease_path = tile_queue.processing_dir / f"{tile_path.name}.lease.json"
            if lease_path.exists():
                try:
                    with lease_path.open() as lf:
                        lease = json.load(lf)
                        worker_id = lease["worker_id"]
                        claimed_at = datetime.fromisoformat(lease["claimed_at"])
                        expires_at = datetime.fromisoformat(lease["expires_at"])
                        age_min = (datetime.now(UTC) - claimed_at).total_seconds() / 60
                        ttl_min = (expires_at - datetime.now(UTC)).total_seconds() / 60
                        if ttl_min > 0:
                            status = f"TTL: {ttl_min:.0f}min"
                            style = "green"
                        else:
                            status = "EXPIRED"
                            style = "red"
                        console.print(f"  • {tile_path.name}: {worker_id} (claimed {age_min:.0f}min ago) [{style}]{status}[/{style}]")
                except Exception as e:
                    console.print(f"  • {tile_path.name}: [error]Error reading lease: {e}[/error]")
            else:
                console.print(f"  • {tile_path.name}: [warning]No lease file[/warning]")

    if expired_count > 0:
        console.print(f"\n[bold red][ALERT][/bold red] {expired_count} tile(s) have expired leases")
        console.print("[dim]These will be automatically reclaimed on next worker scan (~5s)[/dim]")
    elif processing_count == 0:
        console.print("\n[green][OK] Queue idle, no processing tiles[/green]")
    else:
        console.print(f"\n[green][OK] {processing_count} tile(s) processing, no expired leases[/green]")


@queue_app.command(name="purge-leases")
def purge_stale_leases(
    campaign: str = typer.Option("", help="Campaign name"),
    queue_name: str = typer.Option("gm-list", help="Queue name (gm-list, map-tile, etc)"),
    force: bool = typer.Option(False, help="Force remove ALL leases (even fresh ones)"),
    dry_run: bool = typer.Option(False, help="Preview what would be deleted without deleting"),
    max_age_minutes: int = typer.Option(30, help="Lease is stale if heartbeat older than N minutes"),
) -> None:
    """
    Purge stale or expired leases from a queue directory.

    Leases can block work from being claimed if they're left behind by
    crashed or abandoned workers. This command removes them to unblock
    the queue.

    USAGE:
      # Remove expired leases (default 30min old):
      cocli audit queue purge-leases turboship

      # Preview without deleting:
      cocli audit queue purge-leases turboship --dry-run

      # Force remove ALL leases (for testing/reset):
      cocli audit queue purge-leases turboship --force

      # Custom age threshold:
      cocli audit queue purge-leases turboship --max-age-minutes 10
    """
    from cocli.services.lease_cleanup import purge_expired_leases, force_purge_all_leases
    from cocli.core.config import get_campaign

    campaign_name = campaign or get_campaign() or "default"
    queue_dir = paths.campaign(campaign_name).queue(queue_name).pending

    console.print(f"[bold blue]Lease Cleanup: {campaign_name} / {queue_name}[/bold blue]")
    console.print(f"  Directory: {queue_dir}\n")

    if dry_run:
        console.print("[yellow]DRY RUN MODE - no files will be deleted[/yellow]\n")

    if force:
        console.print("[bold red]WARNING: Force mode will delete ALL leases[/bold red]")
        if not dry_run:
            confirm = Prompt.ask("Type 'yes' to confirm", default="no")
            if confirm.lower() != "yes":
                console.print("[yellow]Cancelled[/yellow]")
                return

        metrics = force_purge_all_leases(queue_dir, dry_run=dry_run)
        console.print("\n[bold]Results:[/bold]")
        console.print(f"  Leases found:  {metrics['leases_found']}")
        console.print(f"  Leases deleted: {metrics['leases_deleted']}")
        if metrics["errors"] > 0:
            console.print(f"  [red]Errors: {metrics['errors']}[/red]")
    else:
        metrics = purge_expired_leases(queue_dir, max_heartbeat_age_minutes=max_age_minutes, dry_run=dry_run)
        console.print("\n[bold]Results:[/bold]")
        console.print(f"  Leases found:   {metrics['leases_found']}")
        console.print(f"  Leases expired: {metrics['leases_expired']}")
        console.print(f"  Leases deleted: {metrics['leases_deleted']}")
        if metrics["errors"] > 0:
            console.print(f"  [red]Errors: {metrics['errors']}[/red]")

    if dry_run:
        console.print("\n[dim][DRY RUN] No files were actually deleted[/dim]")
    elif metrics["leases_deleted"] > 0:
        console.print(f"\n[green]✓ Cleaned up {metrics['leases_deleted']} stale lease(s)[/green]")
