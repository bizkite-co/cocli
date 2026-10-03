from __future__ import annotations

import typer
from rich.console import Console

from cocli.models.domain_record import DomainRecord

app = typer.Typer(no_args_is_help=True, help="Domain-wide records shared across every company on that domain.")
console = Console()


@app.command(name="set-employee-directory")
def set_employee_directory(
    domain: str = typer.Argument(..., help="Domain, e.g. higginbotham.com"),
    url: str = typer.Argument(..., help="URL of the employee directory page"),
) -> None:
    """Record where to find this domain's employee directory - not
    scraped, just a reference so there's one obvious place to look when
    hunting for a person's contact info."""
    record = DomainRecord.get_or_create(domain)
    record.employee_directory_url = url
    path = record.save()
    console.print(f"[bold green]Saved[/bold green] {path}")
    console.print(f"  employee_directory_url: {url}")


@app.command(name="show")
def show(domain: str = typer.Argument(..., help="Domain, e.g. higginbotham.com")) -> None:
    """Show the domain-wide record for a domain, if one exists."""
    record = DomainRecord.get(domain)
    if not record:
        console.print(f"[yellow]No domain record for {domain} yet.[/yellow]")
        return

    console.print(f"[bold]Domain:[/bold] {record.domain}")
    console.print(f"[bold]Employee directory:[/bold] {record.employee_directory_url or '(not set)'}")
    if record.notes:
        console.print(f"[bold]Notes:[/bold] {record.notes}")
    console.print(f"[dim]Updated: {record.updated_at.strftime('%Y-%m-%d %H:%M')} UTC[/dim]")
