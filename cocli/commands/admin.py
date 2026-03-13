import typer
import os
import shutil
from pathlib import Path
from rich.console import Console
from rich.prompt import Confirm
from cocli.core.environment import get_environment, Environment

app = typer.Typer(help="Administrative commands for system management.")
console = Console()

def get_prod_root() -> Path:
    """Returns the absolute root for PROD data."""
    if "COCLI_DATA_HOME" in os.environ:
        return Path(os.environ["COCLI_DATA_HOME"]).expanduser().resolve()
    
    import platform
    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "cocli"
    elif platform.system() == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "cocli"
    else:
        base = Path.home() / ".local" / "share" / "cocli"
    return base / "data"

@app.command(name="refresh-dev")
def refresh_dev(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt.")
) -> None:
    """
    Refreshes the local DEV environment data from PROD.
    WARNING: This will OVERWRITE existing DEV data.
    """
    env = get_environment()
    if env == Environment.PROD:
        console.print("[red bold]ERROR: Cannot run refresh-dev while in PROD mode.[/red bold]")
        console.print("Set COCLI_ENV=dev to use this command.")
        raise typer.Exit(1)

    prod_root = get_prod_root()
    target_root = prod_root.parent / f"{prod_root.name}_{env.value}"

    if not prod_root.exists():
        console.print(f"[red]ERROR: PROD data not found at {prod_root}[/red]")
        raise typer.Exit(1)

    console.print("[bold]Refresh Plan:[/bold]")
    console.print(f"  Source (PROD): {prod_root}")
    console.print(f"  Target ({env.value.upper()}): {target_root}")
    
    if not force:
        if not Confirm.ask(f"Are you sure you want to OVERWRITE {env.value.upper()} data with PROD data?"):
            console.print("[yellow]Refresh cancelled.[/yellow]")
            return

    try:
        if target_root.exists():
            console.print(f"[dim]Removing existing {env.value.upper()} data...[/dim]")
            shutil.rmtree(target_root)
        
        console.print("[bold cyan]Copying data (this may take a while)...[/bold cyan]")
        # Use shutil.copytree for a full duplicate
        # TODO: Implement 'minimization' logic later if needed
        shutil.copytree(prod_root, target_root, symlinks=True)
        
        console.print(f"[bold green]Successfully refreshed {env.value.upper()} environment![/bold green]")
    except Exception as e:
        console.print(f"[red bold]Refresh failed: {e}[/red bold]")
        raise typer.Exit(1)
