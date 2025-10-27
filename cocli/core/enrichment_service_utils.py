
import subprocess
import httpx
import typer
from rich.console import Console
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def ensure_enrichment_service_ready(console: Console):
    """
    Ensures the enrichment service is running and up-to-date.
    Performs a scraper version check and a health check.
    """
    # --- Check for newer local scraper code ---
    console.print(f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [dim]Checking for newer local website scraper code...[/dim]")
    result = subprocess.run(
        ["./scripts/check_scraper_version.py", "--image-name", "enrichment-service"],
        capture_output=True,
        text=True,
        check=False # Don't raise an exception for non-zero exit codes
    )
    console.print(result.stdout)
    if result.returncode == 1: # Local is newer
        console.print("[bold red]Error: Local website_scraper.py is newer than the one in the 'enrichment-service' Docker image.[/bold red]")
        console.print("[red]Please rebuild the Docker image using 'make docker-build' and restart the container using 'make docker-run-enrichment'.[/red]")
        raise typer.Exit(code=1)

    # --- Health Check for Enrichment Service ---
    console.print(f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [dim]Pinging enrichment service...[/dim]")
    try:
        with httpx.Client() as client:
            response = client.get("http://localhost:8000/health", timeout=5.0)
            response.raise_for_status()
        console.print(f"[grey50][{datetime.now().strftime('%H:%M:%S')}][/] [green]Enrichment service is online.[/green]")
    except httpx.RequestError as e:
        console.print("[bold red]Error: Could not connect to the enrichment service.[/bold red]")
        console.print(
            "[red]Please ensure the Docker container is running: 'docker run -d -p 8000:8000 --name cocli-enrichment enrichment-service'[/red]"
        )
        console.print(f"[dim]Details: {e}[/dim]")
        raise typer.Exit(code=1)

