import typer
from typing import Optional
from rich.console import Console

from ..core.config import get_context, set_context

console = Console()

def context(

    filter_str: Optional[str] = typer.Argument(None, help="The filter to set as the current context (e.g., 'tag:prospect', 'missing:email'). If not provided, shows the current context.")

) -> None:
    """
    Sets, shows, or clears the current context.
    """
    if filter_str is None:
        context_filter = get_context()
        if context_filter:
            console.print(f"Current context is: [bold]{context_filter}[/]")
        else:
            console.print("No context is set.")
    elif filter_str.lower() == "unset":
        set_context(None)
        console.print("[green]Context cleared.[/]")
    else:
        set_context(filter_str)
        console.print(f"[green]Context set to:[/] [bold]{filter_str}[/]")