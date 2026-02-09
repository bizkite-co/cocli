import typer
import logging
from rich.console import Console

console = Console()
logger = logging.getLogger(__name__)

app = typer.Typer(help="Commands for managing sharded indexes.")

@app.command(name="compact")
def compact(
    campaign: str = typer.Option("roadmap", help="Campaign name"),
    index: str = typer.Option("google_maps_prospects", help="Index name to compact"),
    debug: bool = typer.Option(False, help="Enable debug logging")
) -> None:
    """
    Compact the Write-Ahead Log (WAL) into the main Checkpoint.
    Uses S3-Native isolation to prevent race conditions.
    """
    if debug:
        logging.getLogger("cocli").setLevel(logging.DEBUG)
        
    from ..core.compact import CompactManager
    
    console.print(f"[bold blue]Starting compaction for index '{index}' in campaign '{campaign}'...[/bold blue]")
    
    manager = CompactManager(campaign_name=campaign, index_name=index)
    
    try:
        manager.run()
        console.print("[bold green]Compaction complete.[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Compaction failed: {e}[/bold red]")
        if debug:
            import traceback
            console.print(traceback.format_exc())
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
