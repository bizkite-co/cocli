import typer
from pathlib import Path
from rich.console import Console

from ..core.config import get_companies_dir

app = typer.Typer(no_args_is_help=True)
console = Console()

@app.command("list-recent")
def list_recent(
    count: int = typer.Option(10, "--count", "-c", help="The number of recent companies to list.")
):
    """
    Lists the most recently created companies.
    """
    companies_dir = get_companies_dir()
    if not companies_dir.exists():
        console.print("[bold red]Companies directory not found.[/bold red]")
        raise typer.Exit(code=1)

    company_dirs = [d for d in companies_dir.iterdir() if d.is_dir()]
    if not company_dirs:
        console.print("[yellow]No companies found.[/yellow]")
        return

    sorted_dirs = sorted(company_dirs, key=lambda d: d.stat().st_ctime, reverse=True)

    console.print(f"[bold]Most recently created companies:[/bold]")
    for i, company_dir in enumerate(sorted_dirs):
        if i >= count:
            break
        console.print(f"- {company_dir.name}")
