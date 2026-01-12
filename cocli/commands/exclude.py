import typer
from typing import Optional
import logging
from rich.console import Console
from rich.table import Table

from ..core.exclusions import ExclusionManager
from ..core.paths import paths
from ..core.utils import slugify

logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer(help="Manage campaign-specific exclusions")

@app.command(name="add")
def add_exclude(
    target: str = typer.Argument(..., help="Company slug or domain to exclude."),
    campaign: str = typer.Option(..., "--campaign", "-c", help="The campaign slug."),
    reason: Optional[str] = typer.Option(None, "--reason", "-r", help="Reason for exclusion."),
) -> None:
    """
    Excludes a company (by slug or domain) from a campaign.
    """
    manager = ExclusionManager(campaign)
    
    # Try to determine if it's a domain or a slug
    if "." in target and not target.endswith(".com") and not target.endswith(".net"):
        # Very simple heuristic: if it has a dot and isn't obviously a slug, treat as domain
        manager.add_exclusion(domain=target, reason=reason)
        console.print(f"[green]Excluded domain: {target}[/green]")
    else:
        manager.add_exclusion(slug=target, reason=reason)
        console.print(f"[green]Excluded slug: {target}[/green]")

@app.command(name="remove")
def remove_exclude(
    target: str = typer.Argument(..., help="Company slug or domain to remove from exclusion."),
    campaign: str = typer.Option(..., "--campaign", "-c", help="The campaign slug."),
) -> None:
    """
    Removes an exclusion from a campaign.
    """
    manager = ExclusionManager(campaign)
    if "." in target:
        manager.remove_exclusion(domain=target)
    else:
        manager.remove_exclusion(slug=target)
    console.print(f"[green]Removed exclusion for: {target}[/green]")

@app.command(name="list")
def list_excludes(
    campaign: str = typer.Option(..., "--campaign", "-c", help="The campaign slug."),
) -> None:
    """
    Lists all exclusions for a campaign.
    """
    manager = ExclusionManager(campaign)
    exclusions = manager.list_exclusions()
    
    if not exclusions:
        console.print(f"No exclusions found for campaign '{campaign}'.")
        return

    table = Table(title=f"Exclusions for {campaign}")
    table.add_column("Slug")
    table.add_column("Domain")
    table.add_column("Reason")
    table.add_column("Created At")
    
    for exc in exclusions:
        table.add_row(
            exc.company_slug or "-",
            exc.domain or "-",
            exc.reason or "-",
            exc.created_at.strftime("%Y-%m-%d %H:%M:%S")
        )
    
    console.print(table)