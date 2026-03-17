import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table
import json
import duckdb
from ..utils.duckdb_utils import find_datapackage, load_usv_to_duckdb

app = typer.Typer()
console = Console()


@app.command()
def list_schemas() -> None:
    """List all known frictionless data schemas (datapackage.json files) in the project."""
    root = Path.cwd()
    dps = list(root.rglob("datapackage.json"))

    table = Table(title="Known Datapackages")
    table.add_column("Path", style="cyan")
    table.add_column("Resources")

    for dp in dps:
        with open(dp, "r") as f:
            pkg = json.load(f)
            resources = [res.get("name", "unknown") for res in pkg.get("resources", [])]
            table.add_row(str(dp.relative_to(root)), ", ".join(resources))

    console.print(table)


@app.command()
def describe(file_path: Path) -> None:
    """Show the schema definition (fields/types) for a given USV file."""
    if not file_path.exists():
        console.print(f"[red]Error: File not found: {file_path}[/red]")
        raise typer.Exit(1)

    dp_path = find_datapackage(file_path)
    if not dp_path:
        console.print(
            f"[red]Error: Could not find authoritative datapackage.json for: {file_path}[/red]"
        )
        raise typer.Exit(1)

    with open(dp_path, "r") as f:
        pkg = json.load(f)

    resource = None
    filename = file_path.name
    for res in pkg.get("resources", []):
        if res.get("path") == filename:
            resource = res
            break

    if not resource:
        console.print(
            f"[red]Error: No resource found in {dp_path} for: {filename}[/red]"
        )
        raise typer.Exit(1)

    fields = resource.get("schema", {}).get("fields", [])

    console.print(f"[bold]Schema for {file_path.name}[/bold]")
    console.print(f"[dim]from {dp_path}[/dim]")
    for i, field in enumerate(fields):
        console.print(f"{i}: {field['name']} ({field.get('type', 'string')})")


@app.command()
def search(
    file_path: Path,
    query: str = typer.Argument(
        ..., help="SQL-like WHERE clause to search the USV file."
    ),
    columns: str = typer.Option(
        "company_slug, phone, reviews_count", help="Comma-separated columns to select."
    ),
) -> None:
    """Provide a schema-aware search interface for USV files using DuckDB."""
    if not file_path.exists():
        console.print(f"[red]Error: File not found: {file_path}[/red]")
        raise typer.Exit(1)

    con = duckdb.connect(database=":memory:")
    try:
        load_usv_to_duckdb(con, "search_table", file_path)

        sql = f"SELECT {columns} FROM search_table WHERE {query}"
        results = con.execute(sql).fetchall()

        table = Table(title=f"Search Results: {query}")
        for col in [c.strip() for c in columns.split(",")]:
            table.add_column(col)

        for row in results:
            table.add_row(*[str(val) for val in row])

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error querying data: {e}[/red]")
        raise typer.Exit(1)
