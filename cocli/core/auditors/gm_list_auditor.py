from pathlib import Path
from cocli.utils.usv_utils import USVReader, USVWriter
from rich.console import Console
import duckdb

console = Console()


def run_compilation(campaign: str, queue: str, results_dir: Path) -> Path:
    compiled_path = results_dir / "compiled.usv"
    usv_files = [
        f
        for f in results_dir.rglob("*.usv")
        if f.name
        not in [
            "compiled.usv",
            "compacted.usv",
            "results.usv",
            "corrupted-records.usv",
            "results.invalid.usv",
        ]
    ]

    count = 0
    skipped = 0
    with open(compiled_path, "w", encoding="utf-8") as f_out:
        writer = USVWriter(f_out)
        for usv_file in usv_files:
            if not usv_file.exists():
                console.print(f"[red]File disappeared: {usv_file}[/red]")
                continue
            with open(usv_file, "r", encoding="utf-8") as f_in:
                reader = USVReader(f_in)
                try:
                    rows = list(reader)
                except Exception as e:
                    console.print(
                        f"[red]Error reading {usv_file.relative_to(results_dir)}: {e}[/red]"
                    )
                    skipped += 1
                    continue
                if not rows:
                    console.print(
                        f"[yellow]Skipping {usv_file.relative_to(results_dir)}: Empty file[/yellow]"
                    )
                    skipped += 1
                    continue

                num_fields = len(rows[0])
                if num_fields < 9 or num_fields > 10:
                    console.print(
                        f"[yellow]Skipping {usv_file.relative_to(results_dir)}: {num_fields} fields[/yellow]"
                    )
                    skipped += 1
                    continue

                for row in rows:
                    # Pad to 10 fields if necessary
                    if len(row) == 9:
                        row.insert(3, None)  # Insert category at index 3
                    elif len(row) > 10:
                        row = row[:10]
                    elif len(row) < 9:
                        # Skip malformed rows
                        continue

                    writer.writerow(row)
                    count += 1

    console.print(
        f"[green]Compiled {count} records to {compiled_path}. Skipped {skipped} files.[/green]"
    )
    return compiled_path


def run_compaction(results_dir: Path) -> Path:
    compiled_path = results_dir / "compiled.usv"
    compacted_path = results_dir / "compacted.usv"
    invalid_path = results_dir / "results.invalid.usv"

    con = duckdb.connect(database=":memory:")
    con.execute(f"""
        CREATE TABLE raw_data AS 
        SELECT * FROM read_csv('{compiled_path}', delim='\x1f', header=False, auto_detect=False, 
                               columns={{
                                   'place_id': 'VARCHAR', 'company_slug': 'VARCHAR', 'name': 'VARCHAR',
                                   'category': 'VARCHAR', 'phone': 'VARCHAR', 'domain': 'VARCHAR',
                                   'reviews_count': 'VARCHAR', 'average_rating': 'VARCHAR', 
                                   'street_address': 'VARCHAR', 'gmb_url': 'VARCHAR'
                               }}, 
                               quote='', escape='', null_padding=True)
    """)

    # 1. Clean misalignment
    con.execute("""
        UPDATE raw_data
        SET reviews_count = NULL
        WHERE TRY_CAST(reviews_count AS BIGINT) IS NULL 
           OR reviews_count = REGEXP_EXTRACT(phone, '^1?[^\\d]*(\\d{3})', 1)
           OR reviews_count = REGEXP_EXTRACT(street_address, '^(\\d+)', 1)
    """)

    # 2. Filter & Export Invalid
    con.execute(f"""
        COPY (SELECT * FROM raw_data WHERE NOT (
          LENGTH(place_id) BETWEEN 26 AND 29
          AND LENGTH(company_slug) BETWEEN 3 AND 100
          AND LENGTH(name) BETWEEN 1 AND 100
          AND (phone IS NULL OR (LENGTH(phone) BETWEEN 10 AND 15))
          AND (domain IS NULL OR (LENGTH(domain) BETWEEN 3 AND 100))
          AND (reviews_count IS NULL OR TRY_CAST(reviews_count AS BIGINT) >= 0)
          AND (average_rating IS NULL OR (TRY_CAST(average_rating AS DOUBLE) BETWEEN 0.0 AND 5.0))
          AND (street_address IS NULL OR (LENGTH(street_address) BETWEEN 5 AND 100))
          AND (gmb_url IS NULL OR LENGTH(gmb_url) >= 20)
        )) TO '{invalid_path}' (DELIMITER '\x1f', HEADER FALSE)
    """)

    # 3. Create Valid Table
    con.execute("""
        CREATE TABLE valid_data AS
        SELECT * FROM raw_data
        WHERE LENGTH(place_id) BETWEEN 26 AND 29
          AND LENGTH(company_slug) BETWEEN 3 AND 100
          AND LENGTH(name) BETWEEN 1 AND 100
          AND (phone IS NULL OR (LENGTH(phone) BETWEEN 10 AND 15))
          AND (domain IS NULL OR (LENGTH(domain) BETWEEN 3 AND 100))
          AND (reviews_count IS NULL OR TRY_CAST(reviews_count AS BIGINT) >= 0)
          AND (average_rating IS NULL OR (TRY_CAST(average_rating AS DOUBLE) BETWEEN 0.0 AND 5.0))
          AND (street_address IS NULL OR (LENGTH(street_address) BETWEEN 5 AND 100))
          AND (gmb_url IS NULL OR LENGTH(gmb_url) >= 20)
    """)

    # 4. Dedupe
    con.execute("""
        CREATE TABLE final_compacted AS
        SELECT * FROM (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY place_id 
                ORDER BY TRY_CAST(reviews_count AS BIGINT) DESC NULLS LAST
            ) as rn
            FROM valid_data
        ) WHERE rn = 1
    """)
    con.execute("ALTER TABLE final_compacted DROP rn")

    # Export
    records = con.execute("SELECT * FROM final_compacted").fetchall()
    with open(compacted_path, "w", encoding="utf-8") as f_out:
        writer = USVWriter(f_out)
        for row in records:
            writer.writerow(row)

    console.print(
        f"[green]Compacted {len(records)} records to {compacted_path}. Invalid rows to {invalid_path}.[/green]"
    )
    return compacted_path


def run_reporting(results_dir: Path) -> Path:
    from cocli.commands.data import metrics

    # 1. Generate missing_review_count.usv
    missing_path = results_dir.parent / "missing_review_count.usv"
    compacted_path = results_dir / "compacted.usv"

    # Use DuckDB to extract records
    con = duckdb.connect(database=":memory:")
    con.execute(f"""
        CREATE TABLE compacted AS 
        SELECT * FROM read_csv('{compacted_path}', delim='\x1f', header=False, auto_detect=False, 
                               columns={{
                                   'place_id': 'VARCHAR', 'company_slug': 'VARCHAR', 'name': 'VARCHAR',
                                   'category': 'VARCHAR', 'phone': 'VARCHAR', 'domain': 'VARCHAR',
                                   'reviews_count': 'VARCHAR', 'average_rating': 'VARCHAR', 
                                   'street_address': 'VARCHAR', 'gmb_url': 'VARCHAR'
                               }}, 
                               quote='', escape='', null_padding=True)
    """)

    records = con.execute(
        "SELECT place_id, reviews_count FROM compacted WHERE reviews_count IS NULL OR reviews_count = ''"
    ).fetchall()

    with open(missing_path, "w", encoding="utf-8") as f_out:
        writer = USVWriter(f_out)
        writer.writerow(["place_id", "reviews_count"])
        for row in records:
            writer.writerow(row)

    console.print(
        f"[green]Generated {missing_path} with {len(records)} records.[/green]"
    )

    # 2. Run existing metrics command logic
    console.print(
        f"[bold blue]Reporting: Generating metrics for {results_dir.parent}[/bold blue]"
    )

    output_report = results_dir / "metrics.md"
    metrics(file_path=compacted_path, output_path=output_report)

    return output_report
