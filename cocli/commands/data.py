import logging
import duckdb
import json
import typer
import fnmatch
from pathlib import Path
from rich.console import Console
from rich.table import Table
from cocli.utils.usv_utils import USVReader
from ..utils.duckdb_utils import (
    find_datapackage,
    load_usv_to_duckdb,
    match_resource_path,
)

# Set up logging for CLI tools
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command(name="list")
def list_schemas() -> None:
    """List all known frictionless data schemas (datapackage.json files) in the project."""
    root = Path.cwd()
    dps = list(root.rglob("datapackage.json"))

    table = Table(title="Known Datapackages")
    table.add_column("Path", style="cyan")
    table.add_column("Resources")

    for dp in dps:
        try:
            with open(dp, "r") as f:
                pkg = json.load(f)
                resources = [
                    res.get("name", "unknown") for res in pkg.get("resources", [])
                ]
                table.add_row(str(dp.relative_to(root)), ", ".join(resources))
        except Exception as e:
            console.print(f"[red]Error reading {dp}: {e}[/red]")

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
        if match_resource_path(filename, res.get("path", "")):
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
def locate(file_path: Path) -> None:
    """Find and display the datapackage.json for a given file."""
    dp = find_datapackage(file_path)
    if dp:
        console.print(f"[green]Found: {dp}[/green]")
    else:
        console.print("[red]No datapackage.json found[/red]")


@app.command()
def sample(
    file_path: Path,
    limit: int = typer.Option(10, "--limit", "-n"),
    text_only: bool = typer.Option(
        False, "--text", help="Output as plain text for narrow terminals."
    ),
) -> None:
    """Show first N rows with column names from a USV file."""
    if not file_path.exists():
        console.print(f"[red]Error: File not found: {file_path}[/red]")
        raise typer.Exit(1)

    con = duckdb.connect(database=":memory:")
    try:
        load_usv_to_duckdb(con, "sample_table", file_path)
        results = con.execute(f"SELECT * FROM sample_table LIMIT {limit}").fetchall()

        # Get column names
        columns = [
            col[1]
            for col in con.execute("PRAGMA table_info('sample_table')").fetchall()
        ]

        if text_only:
            for row in results:
                for col, val in zip(columns, row):
                    console.print(f"{col}: {val}")
                console.print("-" * 20)
        else:
            table = Table(title=f"Sample: {file_path.name}")
            for col in columns:
                table.add_column(col)
            for row in results:
                table.add_row(*[str(val) for val in row])
            console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def metrics(
    file_path: Path = typer.Argument(..., help="Path to USV file or datapackage.json"),
    resource_name: str = typer.Option(
        None,
        "--resource",
        help="Resource name to use if file_path is a datapackage.json.",
    ),
) -> None:
    """Compute data quality metrics for a USV dataset (or datapackage)."""
    if not file_path.exists():
        console.print(f"[red]Error: File not found: {file_path}[/red]")
        raise typer.Exit(1)

    usv_path = file_path
    dp_path = None

    if file_path.name == "datapackage.json":
        with open(file_path, "r") as f:
            pkg = json.load(f)

        # Find resource
        resource = None
        if resource_name:
            for res in pkg.get("resources", []):
                if res.get("name") == resource_name:
                    resource = res
                    break
        elif pkg.get("resources"):
            resource = pkg["resources"][0]

        if not resource:
            console.print(
                "[red]Error: Could not identify resource in datapackage. Specify --resource.[/red]"
            )
            raise typer.Exit(1)

        # Construct USV path (handle glob patterns by finding first match)
        res_path_pattern = resource.get("path", "")
        matches = list(file_path.parent.glob(res_path_pattern))
        if not matches:
            console.print(
                f"[red]Error: No files found matching {res_path_pattern}[/red]"
            )
            raise typer.Exit(1)

        usv_path = matches[0]  # Use first match
        dp_path = file_path
        console.print(
            f"[dim]Using resource: {resource.get('name', 'unknown')} ({usv_path.name})[/dim]"
        )

    con = duckdb.connect(database=":memory:")
    try:
        load_usv_to_duckdb(con, "metrics_table", usv_path, datapackage_path=dp_path)

        total = con.execute("SELECT COUNT(*) FROM metrics_table").fetchone()[0]

        # Get column names
        cols = [
            col[1]
            for col in con.execute("PRAGMA table_info('metrics_table')").fetchall()
        ]

        table = Table(title=f"Metrics: {usv_path.name}")
        table.add_column("Metric")
        table.add_column("Count")

        table.add_row("Total Records", str(total))

        for col in [
            "phone",
            "domain",
            "reviews_count",
            "average_rating",
            "street_address",
        ]:
            if col in cols:
                count = con.execute(
                    f"SELECT COUNT(*) FROM metrics_table WHERE {col} IS NOT NULL"
                ).fetchone()[0]
                table.add_row(col, str(count))

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


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


@app.command()
def inspect(
    file_path: Path,
    row_number: int = typer.Option(
        1, "--row-number", "-r", help="Row number to inspect (1-indexed)."
    ),
) -> None:
    """Show the index, name, and content for a specific row in a USV file."""
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
        if match_resource_path(filename, res.get("path", "")):
            resource = res
            break

    if not resource:
        console.print(
            f"[red]Error: No resource found in {dp_path} for: {filename}[/red]"
        )
        raise typer.Exit(1)

    fields = resource.get("schema", {}).get("fields", [])

    # Read row
    with open(file_path, "r", encoding="utf-8") as f:
        reader = USVReader(f)
        row = None
        for i, r in enumerate(reader):
            if i == row_number - 1:
                row = r
                break

        if row is None:
            console.print(
                f"[red]Error: Row {row_number} not found in {file_path.name}[/red]"
            )
            raise typer.Exit(1)

    console.print(f"[bold]Inspection for {file_path.name}, Row {row_number}:[/bold]")
    for i, field in enumerate(fields):
        val = row[i] if i < len(row) else ""
        console.print(f"{i}: {field['name']:<20} | {val}")
