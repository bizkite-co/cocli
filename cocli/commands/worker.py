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
) -> None:
    """
    Starts a worker node that polls for Google Maps List tasks and executes them.
    """
    effective_campaign = campaign or os.getenv("CAMPAIGN_NAME") or get_campaign()

    if not effective_campaign:
        logger.error("No campaign specified and no active context.")
        raise typer.Exit(1)

    log_level = logging.DEBUG if debug else logging.INFO
    setup_file_logging("worker_gm_list", console_level=log_level)

    config = load_campaign_config(effective_campaign)
    final_workers = workers if workers != 1 else config.get("prospecting", {}).get("scrape_workers", 1)

    service = WorkerService(effective_campaign)
    asyncio.run(service.run_worker(not headed, debug, workers=final_workers))

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
) -> None:
    """
    Starts a worker node that polls for Google Maps Details tasks (Place IDs) and scrapes them.
    """
    effective_campaign = campaign or os.getenv("CAMPAIGN_NAME") or get_campaign()
    if not effective_campaign:
        logger.error("No campaign specified and no active context.")
        raise typer.Exit(1)
    
    log_level = logging.DEBUG if debug else logging.INFO
    setup_file_logging("worker_gm_details", console_level=log_level)

    config = load_campaign_config(effective_campaign)
    final_workers = workers if workers != 1 else config.get("prospecting", {}).get("details_workers", 1)

    service = WorkerService(effective_campaign)
    asyncio.run(service.run_details_worker(not headed, debug, workers=final_workers))

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
) -> None:
    """
    Starts a worker node that polls for enrichment tasks (Domains) and scrapes them.
    """
    effective_campaign = campaign or os.getenv("CAMPAIGN_NAME") or get_campaign()
    if not effective_campaign:
        logger.error("No campaign specified and no active context.")
        raise typer.Exit(1)
    
    log_level = logging.DEBUG if debug else logging.INFO
    setup_file_logging("worker_enrichment", console_level=log_level)

    config = load_campaign_config(effective_campaign)
    final_workers = workers if workers != 1 else config.get("prospecting", {}).get("enrichment_workers", 1)

    service = WorkerService(effective_campaign)
    asyncio.run(service.run_enrichment_worker(not headed, debug, workers=final_workers))
