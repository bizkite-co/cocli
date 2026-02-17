import typer
import logging
from rich.console import Console
from typing import Optional, Dict, Any

from ..application.services import ServiceContainer
from ..renderers import status_renderer
from ..core.config import get_campaign

app = typer.Typer()
console = Console()
logger = logging.getLogger(__name__)

@app.callback(invoke_without_command=True)
def status(
    ctx: typer.Context,
    campaign: Optional[str] = typer.Option(None, help="The campaign to check."),
    refresh: bool = typer.Option(False, "--refresh", "-r", help="Force a fresh stats generation (slow)."),
) -> None:
    """
    Displays the current status of the cocli environment and campaign metrics.
    """
    if ctx.invoked_subcommand:
        return

    effective_campaign = campaign or get_campaign() or "default"
    services = ServiceContainer(campaign_name=effective_campaign)
    
    with console.status("[bold green]Fetching status..."):
        # 1. Get basic environment info
        env = services.reporting_service.get_environment_status()
        
        # 2. Get stats (either from cache or fresh)
        stats: Optional[Dict[str, Any]] = None
        if refresh:
            stats = services.reporting_service.get_campaign_stats(effective_campaign)
        else:
            stats = services.reporting_service.load_cached_report(effective_campaign, "status")
            if not stats:
                console.print("[yellow]No cached report found. Generating fresh stats...[/yellow]")
                stats = services.reporting_service.get_campaign_stats(effective_campaign)

    # 3. Render
    console.print(status_renderer.render_environment_panel(env))
    
    if stats and not stats.get("error"):
        console.print(status_renderer.render_queue_table(stats))
        
        hb_table = status_renderer.render_worker_heartbeat_table(stats)
        if hb_table:
            console.print(hb_table)
    elif stats and stats.get("error"):
        console.print(f"[bold red]Error fetching stats: {stats['error']}[/bold red]")

if __name__ == "__main__":
    app()
