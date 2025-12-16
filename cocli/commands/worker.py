import typer
import asyncio
import logging
import boto3
import csv # Added for details worker to read CSV
from datetime import datetime # Added for updated_at
from rich.console import Console
from playwright.async_api import async_playwright

from cocli.core.logging_config import setup_file_logging
from cocli.core.queue.factory import get_queue_manager
from cocli.scrapers.google_maps import scrape_google_maps
from cocli.scrapers.google_maps_details import scrape_google_maps_details
from cocli.models.scrape_task import GmItemTask
from cocli.models.google_maps_prospect import GoogleMapsProspect
from cocli.models.queue import QueueMessage
from cocli.core.prospects_csv_manager import ProspectsIndexManager
from cocli.core.text_utils import slugify

logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer(no_args_is_help=True)

# ... (rest of the file remains similar until commands)

async def run_worker(headless: bool, debug: bool) -> None:
    # ... (function body)

async def run_details_worker(headless: bool, debug: bool) -> None:
    # ... (function body)

@app.command()
def scrape(
    headed: bool = typer.Option(False, "--headed", help="Run browser in headed mode."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging.")
) -> None:
    """
    Starts a worker node that polls for scrape tasks and executes them.
    """
    log_level = logging.DEBUG if debug else logging.INFO
    setup_file_logging("worker_scrape", console_level=log_level)
    asyncio.run(run_worker(not headed, debug))

@app.command()
def details(
    headed: bool = typer.Option(False, "--headed", help="Run browser in headed mode."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging.")
) -> None:
    """
    Starts a worker node that polls for details tasks (Place IDs) and scrapes them.
    """
    log_level = logging.DEBUG if debug else logging.INFO
    setup_file_logging("worker_details", console_level=log_level)
    asyncio.run(run_details_worker(not headed, debug))

if __name__ == "__main__":
    app()
