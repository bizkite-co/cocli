import typer
from rich.console import Console
from ...application.event_generator_service import EventGeneratorService
from ...core.config import get_campaign

app = typer.Typer(help="Commands for managing campaign events.")
console = Console()

@app.command(name="generate-tasks")
def generate_tasks(
    campaign: str = typer.Option(None, help="Campaign name (defaults to active)"),
    windows: int = typer.Option(1, help="Number of time windows ahead to generate")
) -> None:
    """
    Hydrates EventSource templates into time-specific EventScrapeTasks.
    """
    campaign_name = campaign or get_campaign() or "fullertonian"
    service = EventGeneratorService(campaign_name=campaign_name)
    
    console.print(f"[bold cyan]Generating event discovery tasks for {campaign_name}...[/bold cyan]")
    
    try:
        tasks = service.generate_tasks(windows_ahead=windows)
        if not tasks:
            console.print("[yellow]No new tasks generated. (All windows up-to-date).[/yellow]")
        else:
            console.print(f"[green]Successfully generated {len(tasks)} new tasks.[/green]")
            for t in tasks:
                console.print(f"  - {t.source_id} for {t.target_window}")
                
    except Exception as e:
        console.print(f"[bold red]Generation failed:[/bold red] {e}")
        raise typer.Exit(1)
