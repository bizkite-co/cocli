import logging
import duckdb
import json
import typer
from typing import Optional
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

# Queue sub-commands for data operations
queue_app = typer.Typer(help="Queue management commands")
app.add_typer(queue_app, name="queue")

# Cleanup sub-commands
from .cleanup import app as cleanup_app

app.add_typer(cleanup_app, name="cleanup")


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
    """Show the schema definition (fields/types) for a given USV file or datapackage."""
    if not file_path.exists():
        console.print(f"[red]Error: File not found: {file_path}[/red]")
        raise typer.Exit(1)

    # If given a datapackage.json, show first resource's schema
    if file_path.name == "datapackage.json":
        with open(file_path, "r") as f:
            pkg = json.load(f)

        resources = pkg.get("resources", [])
        if not resources:
            console.print("[red]Error: No resources in datapackage[/red]")
            raise typer.Exit(1)

        # Show schema for each resource
        for res in resources:
            fields = res.get("schema", {}).get("fields", [])
            console.print(f"[bold]Schema for {res.get('name', 'unknown')}[/bold]")
            console.print(f"[dim]path: {res.get('path')}[/dim]")
            for i, field in enumerate(fields):
                console.print(f"{i}: {field['name']} ({field.get('type', 'string')})")
            console.print()
        return

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
    output_path: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Write report to file (Markdown)."
    ),
) -> None:
    """Compute data quality metrics for a USV dataset (or datapackage)."""
    console.print(f"DEBUG: metrics called with output_path={output_path}")
    if not file_path.exists():
        console.print(f"[red]Error: File not found: {file_path}[/red]")
        raise typer.Exit(1)

    usv_path = file_path

    # Handle datapackage.json input
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
        console.print(
            f"[dim]Using resource: {resource.get('name', 'unknown')} ({usv_path.name})[/dim]"
        )

    # Get schema from datapackage for proper column mapping
    from cocli.utils.duckdb_utils import find_datapackage, get_schema_field_names

    dp_path = find_datapackage(usv_path)
    if not dp_path:
        console.print(f"[red]Error: Could not find datapackage for {usv_path}[/red]")
        raise typer.Exit(1)

    # Load schema with field types
    import json

    with open(dp_path, "r") as f:
        pkg = json.load(f)

    resource = pkg.get("resources", [{}])[0]
    schema_fields = get_schema_field_names(dp_path)
    fields_info = {
        f["name"]: f.get("type", "string")
        for f in resource.get("schema", {}).get("fields", [])
    }
    print(f"DEBUG: Schema has {len(schema_fields)} fields: {schema_fields[:5]}...")

    # Build metrics using DuckDB with schema awareness
    con = duckdb.connect(database=":memory:")
    try:
        # Use load_usv_to_duckdb which properly applies the datapackage schema
        from cocli.utils.duckdb_utils import load_usv_to_duckdb

        load_usv_to_duckdb(con, "metrics_data", usv_path, dp_path)

        # Verify column names from loaded table
        cols_info = con.execute("PRAGMA table_info('metrics_data')").fetchall()
        loaded_cols = [c[1] for c in cols_info]
        print(f"DEBUG: Loaded table has columns: {loaded_cols[:5]}...")

        # Dedupe by place_id (using correct column name from schema)
        place_id_col = "place_id" if "place_id" in loaded_cols else loaded_cols[0]

        # Get total unique records
        total = con.execute(
            f"SELECT COUNT(DISTINCT {place_id_col}) FROM metrics_data"
        ).fetchone()[0]

        # Build metrics dict - count non-null, non-empty values for each field
        # Handle numeric fields differently to avoid type conversion errors
        metrics = {"Total Records": total}

        for field in schema_fields:
            if field in loaded_cols:
                field_type = fields_info.get(field, "string")

                if field_type in ("integer", "number"):
                    # For numeric fields, use TRY_CAST to handle empty strings gracefully
                    count = con.execute(
                        f'SELECT COUNT(*) FROM metrics_data WHERE TRY_CAST("{field}" AS VARCHAR) IS NOT NULL AND TRY_CAST("{field}" AS VARCHAR) != \'\' AND TRY_CAST("{field}" AS VARCHAR) != \'NULL\''
                    ).fetchone()[0]
                else:
                    # For string fields, count non-null and non-empty
                    count = con.execute(
                        f'SELECT COUNT(*) FROM metrics_data WHERE "{field}" IS NOT NULL AND "{field}" != \'\' AND "{field}" != \'NULL\''
                    ).fetchone()[0]

                if count > 0:
                    metrics[field] = count

        table = Table(title=f"Metrics: {usv_path.name}")
        table.add_column("Metric")
        table.add_column("Count")

        for metric, count in metrics.items():
            table.add_row(metric, str(count))

        console.print(table)

        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(f"# Metrics: {usv_path.name}\n\n")
                f.write("| Metric | Count |\n")
                f.write("| :--- | :--- |\n")
                for metric, count in metrics.items():
                    f.write(f"| {metric} | {count} |\n")
            console.print(f"[green]Metrics report written to {output_path}[/green]")

        return  # Success with DuckDB

    except Exception as e:
        print(f"DEBUG: DuckDB approach failed: {e}")
        console.print("[yellow]Falling back to Python processing...[/yellow]")

        # Fallback: Python-based metrics (less efficient but works without DuckDB schema)
        import csv
        import sys

        csv.field_size_limit(sys.maxsize)

        # Get field indices from schema
        field_index = {name: i for i, name in enumerate(schema_fields)}

        place_ids = set()
        field_counts = {f: set() for f in schema_fields}

        with open(usv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\x1f")
            prev_place_id = None
            for row in reader:
                if len(row) < len(schema_fields):
                    continue

                place_id = row[0]
                if place_id == prev_place_id:
                    continue  # Skip duplicates
                prev_place_id = place_id
                place_ids.add(place_id)

                # Count non-empty values for each field
                for field_name, idx in field_index.items():
                    if idx < len(row):
                        val = row[idx].strip()
                        if val and val.lower() != "null":
                            field_counts[field_name].add(val)

        total = len(place_ids)
        metrics = {"Total Records": total}
        for field, values in field_counts.items():
            if values:
                metrics[field] = len(values)

        table = Table(title=f"Metrics: {usv_path.name} (fallback)")
        table.add_column("Metric")
        table.add_column("Count")

        for metric, count in metrics.items():
            table.add_row(metric, str(count))

        console.print(table)

        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(f"# Metrics: {usv_path.name} (fallback)\n\n")
                f.write("| Metric | Count |\n")
                f.write("| :--- | :--- |\n")
                for metric, count in metrics.items():
                    f.write(f"| {metric} | {count} |\n")
            console.print(f"[green]Metrics report written to {output_path}[/green]")


@app.command()
def search(
    file_path: Path,
    query: str = typer.Argument(
        ..., help="SQL-like WHERE clause to search the USV file."
    ),
    columns: str = typer.Option(
        "slug, phone, reviews_count", help="Comma-separated columns to select."
    ),
) -> None:
    """Provide a schema-aware search interface for USV files using DuckDB."""
    if not file_path.exists():
        console.print(f"[red]Error: File not found: {file_path}[/red]")
        raise typer.Exit(1)

    # Get schema from datapackage for validation and normalization
    from cocli.utils.duckdb_utils import (
        find_datapackage,
        get_schema_field_names,
        normalize_column_names,
        validate_query_columns,
    )

    dp_path = find_datapackage(file_path)
    if not dp_path:
        console.print(
            f"[yellow]Warning: No datapackage.json found. Schema validation disabled.[/yellow]"
        )
        schema_fields = []
    else:
        schema_fields = get_schema_field_names(dp_path)
        # Validate query columns against schema
        invalid_cols = validate_query_columns(query, schema_fields)
        if invalid_cols:
            console.print(
                f"[red]Error: Unknown column(s) in query: {invalid_cols}[/red]"
            )
            console.print(f"[dim]Valid columns: {schema_fields[:10]}...[/dim]")
            raise typer.Exit(1)

        # Normalize column names (handle aliases like company_slug -> slug)
        columns = normalize_column_names(columns, schema_fields)

    con = duckdb.connect(database=":memory:")
    try:
        load_usv_to_duckdb(con, "search_table", file_path)

        sql = f"SELECT {columns} FROM search_table WHERE {query}"
        results = con.execute(sql).fetchall()

        table = Table(title=f"Search Results: {query}")
        # Use actual column names from the result
        if results:
            # Get column names from result
            result_cols = [desc[0] for desc in con.execute(sql).description]
            for col in result_cols:
                table.add_column(col)
        else:
            # Fallback to normalized input columns
            for col in [c.strip() for c in columns.split(",")]:
                if col != "*":
                    table.add_column(col)

        for row in results:
            table.add_row(*[str(val) if val is not None else "NULL" for val in row])

        console.print(table)
        console.print(f"[dim]{len(results)} rows returned[/dim]")

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


@app.command()
def commit(
    message: str = typer.Option(..., "--message", "-m", help="Commit message"),
) -> None:
    """Commit changes in the current data directory."""
    import subprocess

    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", message], check=True)
        console.print(f"[green]Successfully committed changes: {message}[/green]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error committing changes: {e}[/red]")
        raise typer.Exit(1)
