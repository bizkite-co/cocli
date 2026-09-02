from __future__ import annotations
import typer
from typing import Optional
import logging
from rich.console import Console
from rich.table import Table

from ..core.do_not_call_manager import DoNotCallManager

logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer(
    help="Manage the shared, company-wide do-not-call list (keyed by phone number).",
    no_args_is_help=True,
)


@app.command(name="add", no_args_is_help=True)
def add_do_not_call(
    phone: str = typer.Argument(..., help="Phone number to add to the do-not-call list."),
    reason: Optional[str] = typer.Option(None, "--reason", "-r", help="Reason for the do-not-call entry."),
) -> None:
    """
    Adds a phone number to the shared do-not-call list. Applies across all
    campaigns - the obligation follows the person, not a campaign.
    """
    manager = DoNotCallManager()
    try:
        entry = manager.add(phone, reason=reason)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Added to do-not-call: {entry.phone}[/green]")


@app.command(name="remove", no_args_is_help=True)
def remove_do_not_call(
    phone: str = typer.Argument(..., help="Phone number to remove from the do-not-call list."),
) -> None:
    """
    Removes a phone number from the shared do-not-call list.
    """
    manager = DoNotCallManager()
    if manager.remove(phone):
        console.print(f"[green]Removed from do-not-call: {phone}[/green]")
    else:
        console.print(f"[yellow]Not found on do-not-call list: {phone}[/yellow]")


@app.command(name="list")
def list_do_not_call() -> None:
    """
    Lists every phone number on the shared do-not-call list.
    """
    manager = DoNotCallManager()
    entries = manager.list_entries()

    if not entries:
        console.print("Do-not-call list is empty.")
        return

    table = Table(title="Do-Not-Call (shared, all campaigns)")
    table.add_column("Phone")
    table.add_column("Reason")
    table.add_column("Added At")

    for entry in entries:
        table.add_row(
            entry.phone,
            entry.reason or "-",
            entry.added_at.strftime("%Y-%m-%d %H:%M:%S"),
        )

    console.print(table)
