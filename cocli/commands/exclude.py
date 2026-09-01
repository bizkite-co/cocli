import typer
from typing import Optional
import logging
from rich.console import Console
from rich.table import Table

from ..core.exclusions import ExclusionManager

logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer(help="Manage campaign and shared exclusions", no_args_is_help=True)

SCOPE_HELP = "'campaign' (default, this campaign only) or 'global' (shared, applies to every campaign)."


def _manager(campaign: Optional[str], scope: str) -> ExclusionManager:
    if scope not in ("campaign", "global"):
        console.print(f"[red]Invalid --scope '{scope}': must be 'campaign' or 'global'.[/red]")
        raise typer.Exit(1)
    if scope == "global":
        return ExclusionManager(campaign or "", global_scope=True)
    if not campaign:
        console.print("[red]--campaign is required unless --scope global is set.[/red]")
        raise typer.Exit(1)
    return ExclusionManager(campaign)


@app.command(name="add", no_args_is_help=True)
def add_exclude(
    target: str = typer.Argument(..., help="Company slug or domain to exclude."),
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="The campaign slug (required unless --scope global)."),
    reason: Optional[str] = typer.Option(None, "--reason", "-r", help="Reason for exclusion."),
    scope: str = typer.Option("campaign", "--scope", help=SCOPE_HELP),
) -> None:
    """
    Excludes a company (by slug or domain) from a campaign, or globally
    from every campaign (--scope global).
    """
    manager = _manager(campaign, scope)

    # Try to determine if it's a domain or a slug
    if "." in target and not target.endswith(".com") and not target.endswith(".net"):
        # Very simple heuristic: if it has a dot and isn't obviously a slug, treat as domain
        manager.add_exclusion(domain=target, reason=reason)
        console.print(f"[green]Excluded domain ({scope}): {target}[/green]")
    else:
        manager.add_exclusion(slug=target, reason=reason)
        console.print(f"[green]Excluded slug ({scope}): {target}[/green]")

@app.command(name="remove", no_args_is_help=True)
def remove_exclude(
    target: str = typer.Argument(..., help="Company slug or domain to remove from exclusion."),
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="The campaign slug (required unless --scope global)."),
    scope: str = typer.Option("campaign", "--scope", help=SCOPE_HELP),
) -> None:
    """
    Removes an exclusion from a campaign, or from the global list (--scope global).
    """
    manager = _manager(campaign, scope)
    if "." in target:
        manager.remove_exclusion(domain=target)
    else:
        manager.remove_exclusion(slug=target)
    console.print(f"[green]Removed exclusion ({scope}) for: {target}[/green]")

@app.command(name="list")
def list_excludes(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="The campaign slug (required unless --scope global)."),
    scope: str = typer.Option("campaign", "--scope", help=SCOPE_HELP),
) -> None:
    """
    Lists exclusions for a campaign, or the shared global list (--scope global).
    """
    manager = _manager(campaign, scope)
    exclusions = manager.list_exclusions()

    title = "Global exclusions (all campaigns)" if scope == "global" else f"Exclusions for {campaign}"
    if not exclusions:
        console.print(f"No exclusions found ({title}).")
        return

    table = Table(title=title)
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
