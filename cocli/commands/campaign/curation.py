import typer
import logging
from typing import Optional, List
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
import sys
import termios
import tty

from ...services.event_service import EventService
from ...core.config import get_campaign

from ...models.campaigns.events import Event

app = typer.Typer(no_args_is_help=True)
console = Console()
logger = logging.getLogger(__name__)

def get_char() -> str:
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

def render_event_table(events: List[Event], selected_index: int) -> Table:
    table = Table(box=None, expand=True)
    table.add_column("", width=3)
    table.add_column("Date", width=15)
    table.add_column("Event Name")
    table.add_column("Host", width=20)
    table.add_column("Excl", width=5, justify="center")
    table.add_column("High", width=5, justify="center")

    for i, event in enumerate(events):
        prefix = ">" if i == selected_index else " "
        
        style = "bold white" if i == selected_index else "dim white"
        if event.is_excluded:
            style = "red dim"
        elif event.is_highlighted:
            style = "green bold"

        exclude_mark = "[red]X[/red]" if event.is_excluded else "-"
        highlight_mark = "[green]✓[/green]" if event.is_highlighted else "-"

        table.add_row(
            prefix,
            event.start_time.strftime("%Y-%m-%d %H:%M"),
            event.name,
            event.host_name,
            exclude_mark,
            highlight_mark,
            style=style
        )
    return table

@app.command(name="curate-events")
def curate_events(
    campaign_name: Optional[str] = typer.Argument(None),
) -> None:
    """
    Interactive CLI tool to review and curate upcoming events.
    Navigation: j/k (Up/Down), d (Exclude), l (Highlight), q (Exit)
    """
    if campaign_name is None:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    service = EventService(campaign_name)
    events = service.get_upcoming_events()

    if not events:
        console.print("[yellow]No upcoming events found in WAL.[/yellow]")
        return

    selected_index = 0
    
    with Live(console=console, screen=True, auto_refresh=False) as live:
        while True:
            # Render UI
            content = render_event_table(events, selected_index)
            footer = Panel(
                " [bold]j/k[/bold]: Up/Down | [bold]d[/bold]: Toggle Exclude | [bold]l[/bold]: Toggle Highlight | [bold]q[/bold]: Quit",
                style="dim"
            )
            
            layout = Layout()
            layout.split_column(
                Layout(Panel(content, title=f"Event Curation: {campaign_name}", subtitle=f"Total: {len(events)}"), name="main"),
                Layout(footer, name="footer", size=3)
            )
            
            live.update(layout)
            live.refresh()

            # Handle Input
            char = get_char().lower()
            
            if char == 'q':
                break
            elif char == 'j' or char == '\x1b[b': # Down or Arrow Down
                selected_index = min(selected_index + 1, len(events) - 1)
            elif char == 'k' or char == '\x1b[a': # Up or Arrow Up
                selected_index = max(selected_index - 1, 0)
            elif char == 'd':
                events[selected_index] = service.toggle_exclude(events[selected_index])
            elif char == 'l':
                events[selected_index] = service.toggle_highlight(events[selected_index])

    console.clear()
    console.print(f"[bold green]Curation complete for {campaign_name}.[/bold green]")
