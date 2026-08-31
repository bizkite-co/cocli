import typer
from rich.console import Console

from ..application.services import ServiceContainer
from ..core.config import get_campaign

console = Console()


def help_search(
    phrase: str = typer.Argument(
        ...,
        help="Words to search for in each command's name and description (not its options). "
        "Each word is matched independently (all must be found, in any order), and each word "
        "is a real regex - e.g. 'lease' finds purge-leases/active-leases; 'campaign switch' "
        "finds commands mentioning both words anywhere.",
    ),
    limit: int = typer.Option(25, "--limit", "-n", help="Max results to show."),
) -> None:
    """
    Search every cocli command and subcommand's name and description for a
    phrase, so you don't have to already know the exact command name -
    reads the same command tree `cocli audit cli` / docs/cli/actual_tree.txt
    dumps.
    """
    from typer.main import get_command
    from ..main import app as main_app

    click_command = get_command(main_app)
    campaign = get_campaign() or "default"
    services = ServiceContainer(campaign_name=campaign)
    matches = services.codebase_audit_service.search_cli_tree(click_command, phrase, limit=limit)

    if not matches:
        console.print(f"[yellow]No commands matched '{phrase}'.[/yellow]")
        console.print("Try a shorter or different phrase, or run [bold]cocli --help-text[/bold] to browse everything.")
        raise typer.Exit()

    console.print(f"[bold]{len(matches)} match(es) for '{phrase}':[/bold]\n")
    for m in matches:
        console.print(f"  [bold cyan]cocli {m.path}[/bold cyan]")
        if m.description:
            console.print(f"      {m.description}")
        for opt in m.options:
            console.print(f"      [dim]{opt}[/dim]")
        console.print()
