import logging
import asyncio
import os
from typing import Optional
from pathlib import Path
from rich.console import Console

import typer
from ..application.worker_service import WorkerService
from ..core.logging_config import setup_file_logging
from ..core.config import load_campaign_config, get_campaign

# Load Version
def get_version() -> str:
    # 1. Try file in project root (dev mode)
    try:
        root_version = Path(__file__).parent.parent.parent / "VERSION"
        if root_version.exists():
            return root_version.read_text().strip()
    except Exception:
        pass

    # 2. Try file in package dir (installed mode)
    try:
        pkg_version = Path(__file__).parent.parent / "VERSION"
        if pkg_version.exists():
            return pkg_version.read_text().strip()
    except Exception:
        pass

    # 3. Fallback to importlib.metadata
    try:
        from importlib.metadata import version

        return version("cocli")
    except Exception:
        pass

    return "unknown"


VERSION = get_version()

logger = logging.getLogger(__name__)
console = Console()
app = typer.Typer(no_args_is_help=True)


@app.command()
def supervisor(
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name."
    ),
    headed: bool = typer.Option(False, "--headed", help="Run browser in headed mode."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging."),
    interval: int = typer.Option(
        60, "--interval", help="Seconds between config checks."
    ),
) -> None:
    """
    Starts a supervisor that dynamically manages scrape and details workers based on config.
    """
    effective_campaign = campaign or os.getenv("CAMPAIGN_NAME") or get_campaign()

    if not effective_campaign:
        logger.error("No campaign specified and no active context.")
        raise typer.Exit(1)

    log_level = logging.DEBUG if debug else logging.INFO
    setup_file_logging("supervisor", console_level=log_level)

    service = WorkerService(effective_campaign)
    asyncio.run(service.run_supervisor(not headed, debug, interval))


@app.command(name="gm-list")
def gm_list(
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name."
    ),
    headed: bool = typer.Option(False, "--headed", help="Run browser in headed mode."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging."),
    workers: int = typer.Option(
        1, "--workers", "-w", help="Number of concurrent workers."
    ),
    role: str = typer.Option(
        "full", "--role", help="Worker role: 'full', 'scraper', or 'processor'."
    ),
) -> None:
    """
    Starts a worker node that polls for Google Maps List tasks and executes them.
    """
    effective_campaign = campaign or os.getenv("CAMPAIGN_NAME") or get_campaign()

    if not effective_campaign:
        logger.error("No campaign specified and no active context.")
        raise typer.Exit(1)

    log_level = logging.DEBUG if debug else logging.INFO
    setup_file_logging(f"worker_gm_list_{role}", console_level=log_level)

    config = load_campaign_config(effective_campaign)
    final_workers = workers if workers != 1 else config.get("prospecting", {}).get("scrape_workers", 1)

    service = WorkerService(effective_campaign, role=role)
    asyncio.run(service.run_worker(not headed, debug, workers=final_workers, role=role))

@app.command(name="gm-details")
def gm_details(
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name."
    ),
    headed: bool = typer.Option(False, "--headed", help="Run browser in headed mode."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging."),
    workers: int = typer.Option(
        1, "--workers", "-w", help="Number of concurrent workers."
    ),
    role: str = typer.Option(
        "full", "--role", help="Worker role: 'full', 'scraper', or 'processor'."
    ),
) -> None:
    """
    Starts a worker node that polls for Google Maps Details tasks (Place IDs) and scrapes them.
    """
    effective_campaign = campaign or os.getenv("CAMPAIGN_NAME") or get_campaign()
    if not effective_campaign:
        logger.error("No campaign specified and no active context.")
        raise typer.Exit(1)
    
    log_level = logging.DEBUG if debug else logging.INFO
    setup_file_logging(f"worker_gm_details_{role}", console_level=log_level)

    config = load_campaign_config(effective_campaign)
    final_workers = workers if workers != 1 else config.get("prospecting", {}).get("details_workers", 1)

    service = WorkerService(effective_campaign, role=role)
    asyncio.run(service.run_details_worker(not headed, debug, workers=final_workers, role=role))

@app.command()
def enrichment(
    campaign: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign name."
    ),
    headed: bool = typer.Option(False, "--headed", help="Run browser in headed mode."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging."),
    workers: int = typer.Option(
        1, "--workers", "-w", help="Number of concurrent workers."
    ),
    role: str = typer.Option(
        "full", "--role", help="Worker role: 'full', 'scraper', or 'processor'."
    ),
) -> None:
    """
    Starts a worker node that polls for enrichment tasks (Domains) and scrapes them.
    """
    effective_campaign = campaign or os.getenv("CAMPAIGN_NAME") or get_campaign()
    if not effective_campaign:
        logger.error("No campaign specified and no active context.")
        raise typer.Exit(1)
    
    log_level = logging.DEBUG if debug else logging.INFO
    setup_file_logging(f"worker_enrichment_{role}", console_level=log_level)

    config = load_campaign_config(effective_campaign)
    final_workers = workers if workers != 1 else config.get("prospecting", {}).get("enrichment_workers", 1)

    service = WorkerService(effective_campaign, role=role)
    asyncio.run(service.run_enrichment_worker(not headed, debug, workers=final_workers))

@app.command()
def orchestrate(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name."),
    headed: bool = typer.Option(False, "--headed", help="Run browser in headed mode."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging."),
) -> None:
    """
    Starts orchestrated workers for this node as defined in the campaign cluster config.
    """
    import socket
    from ..models.campaigns.worker_config import WorkerDefinition
    
    effective_campaign = campaign or os.getenv("CAMPAIGN_NAME") or get_campaign()
    if not effective_campaign:
        logger.error("No campaign specified and no active context.")
        raise typer.Exit(1)

    log_level = logging.DEBUG if debug else logging.INFO
    setup_file_logging("orchestration", console_level=log_level)

    from ..services.cluster_service import ClusterService
    service = ClusterService(effective_campaign)
    
    # Use environment variable if set (standard for our Docker runners), otherwise local hostname
    raw_hostname = os.getenv("COCLI_HOSTNAME") or socket.gethostname()
    hostname = raw_hostname.split(".")[0]
    
    # 1. Resolve Node Config from ClusterService
    node_config = next((n for n in service.get_nodes() if n.hostname.startswith(hostname)), None)
    
    if not node_config:
        logger.warning(f"No specific configuration found for node {hostname} in campaign {effective_campaign}.")
        logger.info("Falling back to default single-worker mode.")
        # Default: 1 gm-list worker
        worker_defs = [WorkerDefinition(name="default", role="full", content_type="gm-list", workers=1, iot_profile=None)]
    else:
        logger.info(f"Found configuration for {node_config.hostname} with {len(node_config.workers)} workers.")
        worker_defs = node_config.workers

    # 2. Execute
    worker_service = WorkerService(effective_campaign)
    asyncio.run(worker_service.run_orchestrated_workers(worker_defs, headless=not headed, debug=debug))

@app.command()
def gossip(
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging."),
) -> None:
    """
    Starts the Gossip Bridge to propagate WAL datagrams across the cluster.
    """
    from ..core.gossip_bridge import GossipBridge
    import time
    
    log_level = logging.DEBUG if debug else logging.INFO
    setup_file_logging("gossip_bridge", console_level=log_level)
    
    logger.info("Starting Gossip Bridge...")
    bridge = GossipBridge()
    bridge.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping Gossip Bridge...")
        bridge.stop()
    except Exception as e:
        logger.error(f"Gossip Bridge crashed: {e}")
        bridge.stop()
        raise typer.Exit(1)
