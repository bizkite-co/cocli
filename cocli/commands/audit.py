import re
import typer
from typing import Optional, Any, List
from pathlib import Path

from rich.console import Console
import duckdb
from ..core.paths import paths
from ..core.config import get_campaign
from ..application.services import ServiceContainer
from rich.table import Table
from rich.prompt import Prompt
from rich.markup import escape
from ..core.queue.task_file_filter import is_valid_task_data_file
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
    from ..core.config import get_campaign
    from ..application.services import ServiceContainer

    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    audit_service = ServiceContainer(campaign_name=campaign_name).queue_audit_service
    state = audit_service.run_queue_gm_list(campaign_name)

    if state == "completed":
        console.print("[green]Audit completed successfully.[/green]")
    else:
        console.print(f"[red]Audit failed in state: {state}[/red]")
        raise typer.Exit(1)


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
    from ..main import app as main_app

    click_command = get_command(main_app)
    campaign = get_campaign() or "default"
    services = ServiceContainer(campaign_name=campaign)
    report = services.codebase_audit_service.get_cli_tree(click_command)

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
    from ..core.audit.fs_auditor import dump_audit_tree
    from io import StringIO

    effective_campaign = campaign or get_campaign() or "default"
    services = ServiceContainer(campaign_name=effective_campaign)

    res = services.codebase_audit_service.audit_filesystem(
        campaign_name=campaign,
        skip_companies=skip_companies,
        gen_cleanup=gen_cleanup,
    )

    root_node = res["root_node"]
    orphans = res["orphans"]
    report_path = res["cleanup_report_path"]

    if gen_cleanup:
        if not orphans:
            console.print("[green]No orphans found. Nothing to clean.[/green]")
        else:
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
    no_duckdb: bool = typer.Option(
        False, "--no-duckdb", help="Force filesystem scan instead of DuckDB.") ,
    summary_only: bool = typer.Option(
        False, "--summary-only", help="Print only JSON summary without Rich table."
    ),
) -> None:
    """Audit the whole scrape workflow for a campaign.

    Syncs Pi queue results and pulls cluster tiles, then reports
    config-derived parameters, discovery/gm-list/gm-details/enrichment
    queue state, and how many discovery tiles have produced gm-list results.
    """
    from ..core.config import get_campaign
    from ..services.cluster_service import ClusterService
    from cocli.application.pi_sync_service import PiSyncService
    from rich.table import Table
    import json
    import asyncio
    import logging

    logger = logging.getLogger(__name__)

    campaign_name = campaign or get_campaign() or "roadmap"

    console.print(
        f"[bold blue]Syncing PI results for campaign: {campaign_name}[/bold blue]"
    )
    sync_service = PiSyncService(campaign_name)
    sync_service.sync_all_nodes(blocking=True)
    console.print("[bold green]Sync Complete![/bold green]")

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

    pending_tiles = staged_tiles - gm_list_tiles

    # Count gm-list queue states directly from filesystem (rglob to handle sharded subdirs)
    gm_list_queue = paths.campaign(campaign_name).queue("gm-list")
    gm_list_pending = 0
    if gm_list_queue.pending.exists():
        gm_list_pending = sum(1 for f in gm_list_queue.pending.rglob("*.usv") if is_valid_task_data_file(f.name))

    gm_list_claimed = 0
    if gm_list_queue.pending.exists():
        gm_list_claimed = len(list(gm_list_queue.pending.rglob("lease*.json")))

    # Count enrichment pipeline queue states via Queue abstractions
    from cocli.core.queue.factory import get_queue_manager
    from cocli.core.ordinant import QueueIdentity

    gm_details_q = get_queue_manager(QueueIdentity.GM_DETAILS, queue_type="gm_list_item", campaign_name=campaign_name)
    enrichment_q = get_queue_manager(QueueIdentity.ENRICHMENT, queue_type="enrichment", campaign_name=campaign_name)

    gm_details_pending = gm_details_q.count_state("pending")
    gm_details_completed = gm_details_q.count_state("completed")
    gm_details_failed = gm_details_q.count_state("failed")

    enrichment_pending = enrichment_q.count_state("pending")
    enrichment_completed = enrichment_q.count_state("completed")
    enrichment_failed = enrichment_q.count_state("failed")


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
        "gm_list_pending": gm_list_pending,
        "gm_list_claimed": gm_list_claimed,
        "gm_list_completed": gm_list_tiles,
        "gm_details_pending": gm_details_pending,
        "gm_details_completed": gm_details_completed,
        "gm_details_failed": gm_details_failed,
        "enrichment_pending": enrichment_pending,
        "enrichment_completed": enrichment_completed,
        "enrichment_failed": enrichment_failed,
        "total_active_scrape_tasks": discovery_valid,
        "valid_business_leads": gm_list_valid,
    }

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
echo '@@HEARTBEAT@@'
# Same stats the S3 heartbeat path trusts (psutil, written by the worker
# itself every push) - docker stats --no-stream is a single noisy instant
# sample and was observed returning "0B / 0B" memory on this cgroup driver.
# The trailing `echo` guarantees a newline before the next marker even
# though `cat` on a no-trailing-newline JSON file won't emit one itself -
# without it the marker glues onto the JSON's closing brace and every
# section after HEARTBEAT silently vanishes into it.
docker exec cocli-supervisor cat /tmp/cocli_heartbeat.json 2>/dev/null || true
echo
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
    # gm-list's real work pool is discovery-gen/completed (a witness-indexed
    # pool the worker walks directly), not queues/gm-list/pending/ - that dir
    # is essentially always empty. Pending = mission tiles minus completion
    # receipts (same {shard}/{lat}/{lon}/{phrase} shape on both sides, just
    # .usv vs .json), a real set-difference rather than a directory count.
    if [ "$q" = "gm-list" ] && [ "$s" = "pending" ]; then
      c=$(comm -23 \
        <(find ~/repos/data/campaigns/__CAMPAIGN__/queues/discovery-gen/completed -name '*.usv' 2>/dev/null | sed 's|.*/completed/||;s|\.usv$||' | sort) \
        <(find ~/repos/data/campaigns/__CAMPAIGN__/queues/gm-list/completed/results -name '*.json' 2>/dev/null | sed 's|.*/results/||;s|\.json$||' | sort) \
        | wc -l)
      echo "$q/$s=$c"
      continue
    fi
    # completed/ for gm-list has a results/ subtree of one receipt per real
    # completion - counting the whole completed/ dir (as the generic branch
    # below does) would pick up other files under it too, so Pending+Done
    # wouldn't sum to the mission total the way it does for every other queue.
    if [ "$q" = "gm-list" ] && [ "$s" = "completed" ]; then
      c=$(find ~/repos/data/campaigns/__CAMPAIGN__/queues/gm-list/completed/results -name '*.json' 2>/dev/null | wc -l)
      echo "$q/$s=$c"
      continue
    fi
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
        "HEADER": [], "HEARTBEAT": [], "WORKERS": [], "ERRORS": [], "ERROR_PATTERNS": [], "LASTLOG": [],
        "TYPE_ACTIVITY": [], "QUEUES": [],
    }
    current = "HEADER"
    markers = {
        "@@HEARTBEAT@@": "HEARTBEAT", "@@WORKERS@@": "WORKERS", "@@ERRORS@@": "ERRORS",
        "@@ERROR_PATTERNS@@": "ERROR_PATTERNS", "@@LASTLOG@@": "LASTLOG",
        "@@TYPE_ACTIVITY@@": "TYPE_ACTIVITY", "@@QUEUES@@": "QUEUES",
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


def _fmt_pct(value: Any) -> str:
    """Colored at-a-glance CPU/MEM reading - lets DEGRADED/STALE verdicts be
    cross-checked against actual load instead of taken on faith. Accepts a
    bare number (S3 heartbeat JSON) or a "NN.NN%" string (docker stats
    --format output from the SSH path) transparently."""
    if value is None:
        return "-"
    try:
        v = float(str(value).rstrip("%"))
    except (TypeError, ValueError):
        return "-"
    text = f"{v:.0f}"
    if v >= 85:
        return f"[red]{text}[/red]"
    if v >= 60:
        return f"[yellow]{text}[/yellow]"
    return text


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


_ERROR_TYPE_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Timeout))\b")


def _classify_error_message(message: str) -> str:
    """Best-effort grouping key for a formatted log message: the exception
    class name if one appears (e.g. "TargetClosedError", "TimeoutError"),
    else the text up to the first colon - good enough to cluster the small
    number of recurring failure shapes seen in practice without needing a
    real log-parsing grammar."""
    match = _ERROR_TYPE_RE.search(message)
    if match:
        return match.group(1)
    return message.split(":", 1)[0].strip() or message.strip()


def _count_error_types(messages: list[str]) -> list[tuple[str, int]]:
    """Counts of _classify_error_message(m) over messages, most frequent
    first (ties broken by first-seen order) - the "list of error types and
    counts" view, since scrolling through 50 raw lines to eyeball repeats
    doesn't scale once a node is actually degraded."""
    counts: dict[str, int] = {}
    for m in messages:
        key = _classify_error_message(m)
        counts[key] = counts.get(key, 0) + 1
    return sorted(counts.items(), key=lambda kv: kv[1], reverse=True)


@app.command(name="cluster")
def audit_cluster(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name (defaults to current)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show each node's raw heartbeat payload (or, with --s3, recent log lines)."),
    use_s3: bool = typer.Option(
        False,
        "--s3", "--fast",
        help="Use the S3 heartbeat fan-in instead of live SSH+docker-logs polling. Avoids "
        "opening an SSH connection per node, at the cost of relying on each node's last "
        "self-reported heartbeat (which can be stale or wrong if the node's own reporting "
        "is broken - the exact case this is meant to help diagnose). Also shows gm-list "
        "Pending as '-' rather than computing it, since that requires a full "
        "discovery-gen/completed listing this flag exists to avoid.",
    ),
) -> None:
    """
    Audit cluster nodes: designation (content_type/workers), queue depths, and a
    health signal (recent errors + staleness). SSHes each node directly and reads
    its live docker logs/queue dirs by default (concurrent per node; S3 heartbeat
    is only consulted to fill in nodes with no SSH endpoint, e.g. Fargate). Pass
    --s3 to instead read purely from each node's last self-reported S3 heartbeat.
    """
    from ..core.config import get_campaign

    campaign_name = campaign or get_campaign() or "roadmap"

    if use_s3:
        _audit_cluster_from_heartbeats(campaign_name, verbose)
        return

    _audit_cluster_ssh(campaign_name, verbose)


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
    #
    # Raw KeyCount under a queue prefix overcounts real tasks: every claimed
    # task adds a lease*.json (and retried ones an attempts*.json) alongside
    # its real data file, and a shared datapackage.json schema sidecar sits
    # in most of these prefixes too - none of those are tasks. Filter with
    # the same is_valid_task_data_file rule FilesystemQueueBase.count_state()
    # already uses locally, so this S3 path and that local path can't drift
    # apart into two different ideas of "how many tasks are pending."
    queue_depths: dict[str, dict[str, int]] = {}
    for q in _KNOWN_CONTENT_TYPES:
        for status in ("pending", "completed", "failed"):
            # gm-list's real work pool is discovery-gen/completed (a witness-
            # indexed pool FilesystemGmListQueue.poll() walks directly), not
            # queues/gm-list/pending/ - that directory is essentially always
            # empty, so counting it renders a real-looking number that has
            # nothing to do with how much work actually remains. The real
            # figure (mission tiles minus completion receipts) IS computable
            # - see _audit_cluster_ssh's QUEUES section - but doing it here
            # would mean paginating the full discovery-gen/completed prefix
            # (tens of thousands of keys) purely to answer this one cell,
            # which is exactly the S3-listing cost --s3 exists to avoid.
            # Leave it uncounted here; use the (default) SSH path for a real
            # number.
            if q == "gm-list" and status == "pending":
                continue
            prefix = f"campaigns/{campaign_name}/queues/{q}/{status}/"
            count = 0
            for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
                for obj in page.get("Contents", []):
                    filename = obj["Key"].rsplit("/", 1)[-1]
                    if is_valid_task_data_file(filename):
                        count += 1
            queue_depths.setdefault(q, {})[status] = count

    now = datetime.now(timezone.utc)

    table = Table(title=f"Cluster Node Audit: {campaign_name}", box=None)
    table.add_column("Node", style="cyan")
    table.add_column("Campaign", style="green")
    table.add_column("Designation", style="magenta")
    table.add_column("CPU %", justify="right")
    table.add_column("MEM %", justify="right")
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
            system: dict[str, Any] = payload.get("system") or {}
            cpu_str = _fmt_pct(system.get("cpu"))
            mem_str = _fmt_pct(system.get("mem"))

            # The node's own report of which campaign it's actually running -
            # not just "which campaign's S3 prefix did we read this from".
            # Older heartbeats (written before this field existed) show "-".
            # A live mismatch against the campaign_name we queried would mean
            # this node's process is running one campaign while its heartbeat
            # landed under another's prefix - flag it instead of hiding it.
            heartbeat_campaign = payload.get("campaign")
            if not heartbeat_campaign:
                campaign_str = "[dim]-[/dim]"
            elif heartbeat_campaign != campaign_name:
                campaign_str = f"[yellow]{escape(str(heartbeat_campaign))} (!= {campaign_name})[/yellow]"
            else:
                campaign_str = str(heartbeat_campaign)

            stale_content_types = [
                ct for ct in designation
                if (age := _age(last_activity.get(ct))) is None or age > _STALE_THRESHOLD_S.get(ct, _DEFAULT_STALE_THRESHOLD_S)
            ]

            designation_str = "\n".join(f"{ct}: {n}" for ct, n in sorted(designation.items())) if designation else "-"
            activity_str = _format_age(last_log_age) if last_log_age is not None else "-"
            health = _node_health_verdict(True, last_log_age, error_count, stale_content_types)
        except Exception as e:
            table.add_row(hostname, "-", "-", "-", "-", "-", "-", f"[red]MALFORMED ({e})[/red]")
            continue

        table.add_row(hostname, campaign_str, designation_str, cpu_str, mem_str, str(error_count), activity_str, health)

    console.print(table)

    queue_table = Table(title=f"Campaign Queue Depths: {campaign_name}", box=None)
    queue_table.add_column("Queue", style="cyan")
    queue_table.add_column("Pending", justify="right")
    queue_table.add_column("Completed", justify="right")
    queue_table.add_column("Failed", justify="right")
    for q in _KNOWN_CONTENT_TYPES:
        depths = queue_depths.get(q, {})
        pending = depths.get("pending")
        pending_str = str(pending) if pending is not None else "-"
        queue_table.add_row(q, pending_str, str(depths.get("completed", 0)), str(depths.get("failed", 0)))
    console.print(queue_table)

    if verbose:
        for hostname in sorted(nodes):
            console.print(
                f"[dim]{hostname} heartbeat:[/dim] {json.dumps(nodes[hostname])}",
                highlight=False,
            )
            recent_errors = nodes[hostname].get("recent_errors") or []
            if recent_errors:
                error_counts = _count_error_types(recent_errors)
                console.print(
                    f"[bold]{hostname} error types (last {len(recent_errors)} messages):[/bold]",
                    highlight=False,
                )
                for error_type, count in error_counts:
                    console.print(
                        f"  [red]{count:>3}[/red]  {escape(error_type)}", highlight=False
                    )
                console.print(
                    f"[bold]{hostname} recent errors (last {len(recent_errors)}):[/bold]",
                    highlight=False,
                )
                for line in recent_errors:
                    console.print(f"  [red]{escape(line)}[/red]", highlight=False)


def _audit_cluster_ssh(campaign_name: str, verbose: bool) -> None:
    """Default path: SSHes each node concurrently and greps its live `docker logs`
    + queue dirs directly. S3 is only consulted to merge in nodes with no SSH
    endpoint (e.g. Fargate) - see `_audit_cluster_from_heartbeats` for the
    S3-heartbeat-only alternative (`--s3`).
    """
    from ..services.cluster_service import ClusterService
    import asyncio
    import json

    service = ClusterService(campaign_name)
    remote_script = _CLUSTER_AUDIT_REMOTE_SCRIPT.replace("__CAMPAIGN__", campaign_name)

    async def collect_node_info(node: Any) -> dict[str, Any]:
        raw = await service.run_remote_command(node, remote_script)
        sections = _parse_cluster_audit_sections(raw)

        live_campaign: Optional[str] = None
        for line in sections["HEADER"]:
            if line.startswith("CAMPAIGN_NAME="):
                live_campaign = line[len("CAMPAIGN_NAME="):].strip()
                break
        has_campaign = live_campaign is not None

        cpu_str = "-"
        mem_str = "-"
        if sections["HEARTBEAT"]:
            try:
                hb = json.loads("\n".join(sections["HEARTBEAT"]))
                # Worker's own self-report, same field the S3 path reads -
                # prefer it over the docker-inspect env var above when present.
                live_campaign = hb.get("campaign") or live_campaign
                has_campaign = live_campaign is not None
                system = hb.get("system") or {}
                cpu_str = _fmt_pct(system.get("cpu"))
                mem_str = _fmt_pct(system.get("mem"))
            except (json.JSONDecodeError, AttributeError):
                pass

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
            "campaign": live_campaign,
            "cpu": cpu_str,
            "mem": mem_str,
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
        return list(await asyncio.gather(*(collect_node_info(n) for n in service.get_nodes())))

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

        system = payload.get("system") or {}
        diagnostics.append({
            "host": hostname,
            "has_campaign": True,
            "campaign": payload.get("campaign"),
            "cpu": _fmt_pct(system.get("cpu")),
            "mem": _fmt_pct(system.get("mem")),
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
    table.add_column("Campaign", style="green")
    table.add_column("Queue", style="magenta")
    table.add_column("Workers", justify="right")
    table.add_column("Pending", justify="right")
    table.add_column("Done", justify="right")
    table.add_column("CPU %", justify="right")
    table.add_column("MEM %", justify="right")
    table.add_column("Errors (30m)", justify="right")
    table.add_column("Last Activity")
    table.add_column("Health")

    for i, d in enumerate(diagnostics):
        if i > 0:
            table.add_section()

        designation = d["designation"]
        # Sorted once, and every per-queue value below is looked up by that
        # same key on the same row - so Workers/Pending/Done for "gm-list"
        # can never land next to a different queue's numbers the way two
        # independently-ordered multi-line cells could.
        relevant_queues = sorted(designation.keys() if designation else d["queue_depths"].keys())

        live_campaign = d.get("campaign")
        if not live_campaign:
            campaign_str = "[dim]-[/dim]"
        elif live_campaign != campaign_name:
            campaign_str = f"[yellow]{escape(str(live_campaign))} (!= {campaign_name})[/yellow]"
        else:
            campaign_str = str(live_campaign)

        cpu_str = d.get("cpu", "-")
        mem_str = d.get("mem", "-")
        error_count = d["error_count"]
        errors_str = str(error_count) if d["has_campaign"] else "-"
        activity_str = _format_age(d["last_log_age"]) if d["last_log_age"] is not None else "-"
        health = _node_health_verdict(d["has_campaign"], d["last_log_age"], error_count, d["stale_content_types"])

        if not relevant_queues:
            table.add_row(d["host"], campaign_str, "-", "-", "-", "-", cpu_str, mem_str, errors_str, activity_str, health)
            continue

        for row_idx, q in enumerate(relevant_queues):
            workers_str = str(designation.get(q, "-")) if designation else "-"
            depths = d["queue_depths"].get(q, {}) if d["queue_depths"] else {}
            pending = depths.get("pending")
            pending_str = str(pending) if pending is not None else "-"
            done_str = str(depths.get("completed", 0)) if d["queue_depths"] else "-"

            is_first = row_idx == 0
            table.add_row(
                d["host"] if is_first else "",
                campaign_str if is_first else "",
                q,
                workers_str,
                pending_str,
                done_str,
                cpu_str if is_first else "",
                mem_str if is_first else "",
                errors_str if is_first else "",
                activity_str if is_first else "",
                health if is_first else "",
            )

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
    from ..core.config import get_campaign
    from ..application.services import ServiceContainer
    from rich.table import Table

    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print("[bold red]Error:[/bold red] No campaign specified.")
        raise typer.Exit(1)

    try:
        audit_service = ServiceContainer(campaign_name=campaign_name).queue_audit_service
        res = audit_service.audit_enrichment(campaign_name)
    except FileNotFoundError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)

    total_companies = res["total_companies"]
    total_enriched = res["total_enriched"]
    has_contact_name = res["has_contact_name"]
    has_phone = res["has_phone"]
    has_email = res["has_email"]
    has_social = res["has_social"]
    tier_1 = res["tier_1"]
    tier_2 = res["tier_2"]
    tier_3 = res["tier_3"]

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
    from ..core.config import get_campaign
    from ..application.services import ServiceContainer
    import webbrowser

    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print("[bold red]Error:[/bold red] No campaign specified.")
        raise typer.Exit(1)

    try:
        audit_service = ServiceContainer(campaign_name=campaign_name).queue_audit_service
        targets = audit_service.get_enrichment_interactive_targets(campaign_name)
    except FileNotFoundError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)

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
            if not domain:
                console.print("[red]No domain available for this company.[/red]")
            else:
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
    from rich.table import Table

    effective_campaign = campaign or get_campaign() or "default"
    services = ServiceContainer(campaign_name=effective_campaign)

    console.print("[bold]Scanning for datapackage.json files...[/bold]\n")

    res = services.codebase_audit_service.audit_schemas(
        campaign=campaign, fix=fix, dry_run=dry_run
    )

    files_checked = res["files_checked"]
    issues_found = res["issues_found"]
    fixed_count = res["fixed_count"]

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
            for issue in issues_found:
                if issue["issue"] in ["MISSING_SCHEMA_HASH", "HASH_MISMATCH"]:
                    console.print(f"  [green]Fixed:[/green] {issue['file']}")

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
    from ..application.services import ServiceContainer

    audit_service = ServiceContainer(campaign_name=campaign).queue_audit_service
    result = audit_service.run_gm_list_html_audit(campaign, limit=limit, output=output)
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
    import sys
    from ..application.services import ServiceContainer

    try:
        audit_service = ServiceContainer(campaign_name=campaign).queue_audit_service
        res = audit_service.prepare_validate(
            campaign=campaign,
            tile=tile,
            phrase=phrase,
            usv_path=usv_path,
            headed=headed,
            limit=limit,
        )
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    records = res["records"]
    already_reviewed = res["already_reviewed"]
    audit_log = res["audit_log"]
    reviewed_path = res["reviewed_path"]
    display_fields = res["display_fields"]
    field_names = res["field_names"]
    mode = res["mode"]
    usv_path_val = res["usv_path"]
    items_scraped_count = res["items_scraped_count"]

    if mode == "online":
        console.print(f"\n[bold yellow]Step 1: Running {'headless' if not headed else 'headed'} scrape...[/bold yellow]")
        if items_scraped_count == 0:
            console.print("[yellow]No items scraped. Skipping review but recording audit log.[/yellow]")
        else:
            console.print(f"[green]  Scraped {items_scraped_count} companies. Saved to results/[/green]")
    else:
        console.print(f"[bold]Offline review:[/bold] [cyan]{usv_path_val}[/cyan]")

    console.print(f"[dim]  Read {len(records)} records from {usv_path_val}[/dim]")
    console.print(f"[green]  Audit log entry saved to {audit_log}[/green]")

    # Step 4: Interactive field-level review
    console.print("\n[bold yellow]Step 4: Field-level review[/bold yellow]")
    console.print("[dim]For each company, review the scraped fields.[/dim]")
    console.print("[dim]    - Press Enter to keep the current value[/dim]")
    console.print("[dim]    - Type a correction to overwrite[/dim]")
    console.print("[dim]    - Type [bold].skip[/bold] to skip this record[/dim]\n")

    try:
        usv_str = str(usv_path_val.resolve())
        parts = usv_str.split("/")
        ref_lat: Optional[str] = None
        ref_lon: Optional[str] = None
        phrase_slug: Optional[str] = None
        try:
            ri = next(i for i, p in enumerate(parts) if p == "results")
            ref_lat = parts[ri + 2]
            ref_lon = parts[ri + 3]
            phrase_slug = parts[ri + 4].replace(".usv", "")
        except (StopIteration, IndexError):
            pass

        if ref_lat and ref_lon and phrase_slug:
            search_url = f"https://www.google.com/maps/search/{phrase_slug}/@{ref_lat},{ref_lon},13z"
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
            if changes:
                for field_name, val in changes.items():
                    audit_service.save_reviewed_item(reviewed_path, place_id, field_name, val)
                corrected_count += len(changes)
            else:
                # Mark as reviewed even if no fields changed
                audit_service.save_reviewed_item(reviewed_path, place_id, "_reviewed", "true")
            
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
    from ..application.services import ServiceContainer

    audit_service = ServiceContainer(campaign_name=campaign).queue_audit_service
    res = audit_service.replay_audit_corrections(
        campaign=campaign,
        usv_path=usv_path,
        output=output,
        corrections_path=corrections_path,
        reviewed_path_opt=reviewed_path_opt,
    )

    console.print(f"[green]  Corrected USV written to: {res['output_path']}[/green]")
    table = Table(title="Replay Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")
    table.add_row("Records in source USV", str(res["records_count"]))
    table.add_row("Field corrections applied", str(res["applied_count"]))
    table.add_row("Rating/review overrides", str(res["reviewed_applied"]))
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
    from ..application.services import ServiceContainer

    try:
        audit_service = ServiceContainer(campaign_name=campaign).queue_audit_service
        res = audit_service.export_cases(campaign=campaign, tile=tile, phrase=phrase)
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    cases_count = res["cases_count"]
    test_cases_path = res["test_cases_path"]
    missing_html = res["missing_html"]

    if cases_count == 0:
        if missing_html:
            console.print(f"[yellow]No cases could be resolved ({missing_html} corrections had no matching HTML files).[/yellow]")
        else:
            console.print("[yellow]No corrections found in reviewed file.[/yellow]")
        return

    console.print(f"[green]  {cases_count} test cases written to: {test_cases_path}[/green]")
    if missing_html:
        console.print(f"[dim]  ({missing_html} corrections skipped — no matching HTML file)[/dim]")


@queue_app.command(name="tile-status")
def queue_status(campaign: str = typer.Option("", help="Campaign name")) -> None:
    """
    Audit tile-queue status: pending/processing/completed tiles with lease info.

    Shows tile queue state, processing tiles with lease expiration, and warns
    about expired leases (stuck tiles that will be reclaimed).
    """
    from ..application.services import ServiceContainer

    campaign_name = campaign or "default"
    audit_service = ServiceContainer(campaign_name=campaign_name).queue_audit_service
    res = audit_service.get_tile_status(campaign_name)

    pending_count = res.pending_count
    processing_count = res.processing_count
    completed_count = res.completed_count
    processing_tiles = res.processing_tiles_details
    expired_count = res.expired_count

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
        for tile in sorted(processing_tiles, key=lambda x: x.tile_name):
            tile_name = tile.tile_name
            if tile.error is not None:
                console.print(f"  • {tile_name}: [error]Error reading lease: {tile.error}[/error]")
            elif tile.no_lease:
                console.print(f"  • {tile_name}: [warning]No lease file[/warning]")
            else:
                worker_id = tile.worker_id
                age_min = tile.age_min if tile.age_min is not None else 0.0
                status = tile.status
                style = tile.style
                console.print(f"  • {tile_name}: {worker_id} (claimed {age_min:.0f}min ago) [{style}]{status}[/{style}]")

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
    from ..application.services import ServiceContainer
    from cocli.core.config import get_campaign

    campaign_name = campaign or get_campaign() or "default"
    audit_service = ServiceContainer(campaign_name=campaign_name).queue_audit_service

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

    res = audit_service.purge_leases(
        campaign_name=campaign_name,
        queue_name=queue_name,
        force=force,
        dry_run=dry_run,
        max_age_minutes=max_age_minutes,
    )
    metrics = res["metrics"]

    console.print("\n[bold]Results:[/bold]")
    if force:
        console.print(f"  Leases found:  {metrics['leases_found']}")
        console.print(f"  Leases deleted: {metrics['leases_deleted']}")
    else:
        console.print(f"  Leases found:   {metrics['leases_found']}")
        console.print(f"  Leases expired: {metrics['leases_expired']}")
        console.print(f"  Leases deleted: {metrics['leases_deleted']}")
    
    if metrics.get("errors", 0) > 0:
        console.print(f"  [red]Errors: {metrics['errors']}[/red]")

    if dry_run:
        console.print("\n[dim][DRY RUN] No files were actually deleted[/dim]")
    elif metrics["leases_deleted"] > 0:
        console.print(f"\n[green]✓ Cleaned up {metrics['leases_deleted']} stale lease(s)[/green]")
