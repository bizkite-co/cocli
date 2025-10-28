import typer
from rich.console import Console

from ..core.config import get_context, get_campaign

app = typer.Typer()
console = Console()

@app.command()
def status() -> None:
    """
    Displays the current status of the cocli environment.
    """
    context_filter = get_context()
    if context_filter:
        console.print(f"Current context is: [bold]{context_filter}[/]")
    else:
        console.print("No context is set.")

    campaign_name = get_campaign()
    if campaign_name:
        console.print(f"Current campaign is: [bold]{campaign_name}[/]")
    else:
        console.print("No campaign is set.")
