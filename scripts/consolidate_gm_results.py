import typer
import logging
from rich.console import Console
from pathlib import Path
from datetime import datetime

app = typer.Typer()
console = Console()

def setup_file_logging(script_name: str) -> Path:
    logs_dir = Path(".logs")
    logs_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"{script_name}_{timestamp}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_file)],
        force=True
    )
    return log_file

@app.command()
def main(
    campaign_name: str = typer.Argument(..., help="Campaign name to consolidate."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Don't perform file operations.")
) -> None:
    """Consolidates high-precision gm-list results into standardized 0.1-degree tiles."""
    if dry_run:
        console.print("[yellow]Dry run not supported via core module yet.[/yellow]")
        return

    console.print(f"Consolidating results for [bold]{campaign_name}[/bold]")
    from cocli.core.prospect_compactor import consolidate_campaign_results
    
    count = consolidate_campaign_results(campaign_name)
    console.print("\n[bold green]Consolidation Complete![/bold green]")
    console.print(f"Files Merged: {count}")

if __name__ == "__main__":
    app()
