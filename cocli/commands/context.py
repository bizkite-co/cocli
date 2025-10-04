import typer
from typing import Optional
from rich.console import Console

from ..core.config import get_context, set_context

app = typer.Typer()
console = Console()

@app.command()
def set(tag: str = typer.Argument(..., help="The tag to set as the current context.")):
    """
    Sets the current context to a specific tag.
    """
    set_context(tag)
    console.print(f"[green]Context set to:[/] [bold]{tag}[/]")

@app.command()
def unset():
    """
    Clears the current context.
    """
    set_context(None)
    console.print("[green]Context cleared.[/]")

@app.command()
def show():
    """
    Displays the current context.
    """
    context_tag = get_context()
    if context_tag:
        console.print(f"Current context is: [bold]{context_tag}[/]")
    else:
        console.print("No context is set.")
