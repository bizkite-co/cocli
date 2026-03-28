from pathlib import Path
import typer
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
                        row.insert(3, None)  # type: ignore[arg-type]
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


def run_html_audit(
    campaign: str,
    limit: int = 200,
    output_name: str = "gm_list_audit",
) -> Path:
    """
    Audit gm-list HTML files to extract and verify rating/review data.

    Uses the same extractors as the real scraping process to verify
    data quality from raw HTML files.

    Args:
        campaign: Campaign name
        limit: Number of random HTML files to audit (default 200)
        output_name: Name for output files

    Returns:
        Path to the audit results USV file
    """
    import random
    from bs4 import BeautifulSoup

    from cocli.core.paths import paths
    from cocli.models.campaigns.indexes.gm_list_audit_item import GmListAuditItem
    from cocli.scrapers.google.google_maps_parsers.extract_rating_reviews_gm_list import (
        extract_rating_reviews_gm_list,
    )
    from cocli.scrapers.google.google_maps_parsers.extract_name import extract_name
    from cocli.scrapers.google.google_maps_parsers.extract_gmb_url_coordinates_place_id import (
        extract_gmb_url_coordinates_place_id,
    )

    campaign_paths = paths.campaign(campaign)
    raw_dir = campaign_paths.path / "raw" / "gm-list"

    if not raw_dir.exists():
        console.print(f"[red]Raw gm-list directory not found: {raw_dir}[/red]")
        raise typer.Exit(1)

    # Find all HTML files
    html_files = list(raw_dir.rglob("*.html"))
    if not html_files:
        console.print(f"[red]No HTML files found in {raw_dir}[/red]")
        raise typer.Exit(1)

    console.print(f"Found {len(html_files)} HTML files. Sampling {limit}...")

    # Random sample
    sample_files = random.sample(html_files, min(limit, len(html_files)))

    audit_items = []

    for html_file in sample_files:
        try:
            with open(html_file, "r", encoding="utf-8") as f:
                html_content = f.read()

            soup = BeautifulSoup(html_content, "html.parser")
            inner_text = soup.get_text()

            # Extract using same functions as real scraper
            name_result = extract_name(soup, inner_text, debug=False)
            rating_result = extract_rating_reviews_gm_list(
                soup, inner_text, debug=False
            )
            url_result = extract_gmb_url_coordinates_place_id(soup, debug=False)

            # Parse rating and reviews
            rating_str = rating_result.get("Average_rating", "")
            reviews_str = rating_result.get("Reviews_count", "")

            rating = float(rating_str) if rating_str else None
            reviews = int(reviews_str) if reviews_str else None

            item = GmListAuditItem(
                place_id=url_result.get("Place_ID", ""),
                name=name_result,
                average_rating=rating,
                reviews_count=reviews,
                gmb_url=url_result.get("GMB_URL", ""),
            )
            audit_items.append(item)

        except Exception as e:
            console.print(f"[yellow]Skipping {html_file.name}: {e}[/yellow]")
            continue

    if not audit_items:
        console.print("[red]No items extracted.[/red]")
        raise typer.Exit(1)

    # Save results
    output_dir = campaign_paths.queue("gm-list").completed / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_usv = output_dir / f"{output_name}.usv"

    # Use BaseUsvModel's save method
    with open(output_usv, "w", encoding="utf-8") as f:
        for item in audit_items:
            f.write(item.to_usv())

    # Save datapackage
    GmListAuditItem.save_datapackage(
        output_dir,
        output_name,
        f"{output_name}.usv",
    )

    console.print(
        f"[green]Audit complete. {len(audit_items)} items saved to {output_usv}[/green]"
    )

    # Print summary
    with_rating = sum(1 for i in audit_items if i.average_rating is not None)
    with_reviews = sum(1 for i in audit_items if i.reviews_count is not None)
    with_both = sum(
        1
        for i in audit_items
        if i.average_rating is not None and i.reviews_count is not None
    )

    console.print("\n[bold]Audit Summary:[/bold]")
    console.print(f"  Total items: {len(audit_items)}")
    console.print(f"  With rating: {with_rating}")
    console.print(f"  With reviews: {with_reviews}")
    console.print(f"  With both: {with_both}")

    return output_usv
