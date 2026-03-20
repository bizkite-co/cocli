"""
GmListResult to GoogleMapsProspect Transformer.

Compacts Google Maps list scraping results (GmListResult USVs) into the main
prospects checkpoint index.

This transformer follows the WAL pattern:
- Sources: GmListResult USVs from PI scrapers (queues/gm-list/completed/results/)
- Destination: GoogleMapsProspect checkpoint (indexes/google_maps_prospects/prospects.checkpoint.usv)
- KEEP source files after transformation (for tracing/debugging)

See docs/pipeline/gm-list/to-google-maps-prospect/README.md for full specification.
"""

import logging
from pathlib import Path

import duckdb

from cocli.core.paths import paths

logger = logging.getLogger(__name__)


def compact_gm_list_results(
    campaign_name: str,
    results_pattern: str | None = None,
) -> int:
    """
    Compacts GmListResult USVs into the prospects checkpoint.

    Args:
        campaign_name: Campaign to process
        results_pattern: Optional glob pattern for results files.
            Defaults to all .usv files in gm-list/completed/results/

    Returns:
        Number of records merged into checkpoint

    Raises:
        ValueError: If campaign has no checkpoint or results directory
    """
    campaign_paths = paths.campaign(campaign_name)

    # Paths
    results_dir = campaign_paths.queue("gm-list").completed / "results"
    checkpoint_path = campaign_paths.index("google_maps_prospects").checkpoint

    if not results_dir.exists():
        logger.warning(f"GmList results directory does not exist: {results_dir}")
        return 0

    if not checkpoint_path.exists():
        logger.warning(f"Checkpoint does not exist: {checkpoint_path}")
        return 0

    if results_pattern is None:
        results_pattern = str(results_dir / "**" / "*.usv")

    logger.info(f"--- GmListResult to GoogleMapsProspect: {campaign_name} ---")
    logger.info(f"Results pattern: {results_pattern}")
    logger.info(f"Checkpoint: {checkpoint_path}")

    con = duckdb.connect(database=":memory:")

    try:
        # 1. Load existing checkpoint
        logger.info("Loading existing checkpoint...")
        checkpoint_dp = (
            campaign_paths.index("google_maps_prospects").path / "datapackage.json"
        )

        if checkpoint_dp.exists():
            _load_usv_with_schema(
                con,
                "checkpoint",
                str(checkpoint_path),
                str(checkpoint_dp),
            )
        else:
            logger.warning("No datapackage.json found, using auto-detection")
            con.execute(f"""
                CREATE TABLE checkpoint AS
                SELECT * FROM read_csv_auto('{checkpoint_path}', delim='\x1f')
            """)

        res = con.execute("SELECT COUNT(*) FROM checkpoint").fetchone()
        checkpoint_count = res[0] if res else 0
        logger.info(f"Checkpoint records: {checkpoint_count}")

        # 2. Load GmListResult files
        logger.info("Loading GmListResult files...")

        # Always use known schema for GmListResult files - they have inconsistent
        # schemas across shards and the subdirectory datapackages may not match
        _load_gm_list_results_auto(con, results_dir)

        res = con.execute("SELECT COUNT(*) FROM gm_results").fetchone()
        results_count = res[0] if res else 0
        logger.info(f"GmListResult records: {results_count}")

        if results_count == 0:
            logger.info("No GmListResult records to merge")
            return 0

        # 3. Merge with deduplication
        logger.info("Merging with deduplication...")

        # Get checkpoint columns
        # Get checkpoint columns
        checkpoint_cols = [
            r[1] for r in con.execute("PRAGMA table_info('checkpoint')").fetchall()
        ]
        logger.info(f"Checkpoint columns: {len(checkpoint_cols)}")

        # Get gm_results columns
        gm_cols = [
            r[1] for r in con.execute("PRAGMA table_info('gm_results')").fetchall()
        ]

        # Map columns using COALESCE for join
        # gm_results has: place_id, company_slug, name, phone, domain, reviews_count,
        #                  average_rating, street_address, gmb_url, discovery_phrase, discovery_tile_id, html
        selects = []
        for col in checkpoint_cols:
            if col == "keyword":
                selects.append("gm.discovery_phrase AS keyword")
            elif col == "place_id":
                selects.append("COALESCE(gm.place_id, cp.place_id) AS place_id")
            elif col in gm_cols:
                selects.append(f"COALESCE(gm.{col}, cp.{col}) AS {col}")
            else:
                selects.append(f"cp.{col}")

        selects_str = ", ".join(selects)

        con.execute("DROP TABLE IF EXISTS merged")
        con.execute(f"""
            CREATE TABLE merged AS
            SELECT * EXCLUDE (rn) FROM (
                SELECT {selects_str},
                    ROW_NUMBER() OVER (
                        PARTITION BY COALESCE(gm.place_id, cp.place_id)
                        ORDER BY COALESCE(cp.updated_at, gm.discovery_tile_id) DESC NULLS LAST
                    ) as rn
                FROM checkpoint cp
                FULL OUTER JOIN gm_results gm ON cp.place_id = gm.place_id
            ) subq WHERE rn = 1
            ORDER BY place_id ASC
        """)

        res = con.execute("SELECT COUNT(*) FROM merged").fetchone()
        merged_count = res[0] if res else 0
        logger.info(f"Merged records: {merged_count}")

        # 4. Write to checkpoint (preserve column order from checkpoint)
        logger.info("Writing to checkpoint...")

        cols_str = ", ".join(checkpoint_cols)
        con.execute(f"""
            COPY (SELECT {cols_str} FROM merged ORDER BY place_id ASC) 
            TO '{checkpoint_path}.tmp' (
                DELIMITER '\x1f',
                HEADER FALSE
            )
        """)

        # 5. Swap files
        backup_path = Path(str(checkpoint_path) + ".bak")
        tmp_path = Path(str(checkpoint_path) + ".tmp")
        Path(checkpoint_path).rename(backup_path)
        tmp_path.rename(checkpoint_path)

        # Keep backup for now (could be removed after verification)
        logger.info(f"Checkpoint updated. Backup: {backup_path}")

        res = con.execute("SELECT COUNT(*) FROM merged").fetchone()
        return int(res[0] if res else 0)

    except Exception as e:
        logger.error(f"Compaction failed: {e}")
        raise
    finally:
        con.close()


def _load_usv_with_schema(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
    usv_path: str,
    datapackage_path: str,
) -> None:
    """Load USV file with schema from datapackage.json."""
    import json

    with open(datapackage_path) as f:
        dp = json.load(f)

    fields = {f["name"]: f["type"] for f in dp["resources"][0]["schema"]["fields"]}

    type_map = {
        "string": "VARCHAR",
        "integer": "BIGINT",
        "number": "DOUBLE",
        "boolean": "BOOLEAN",
    }

    cast_sql = ", ".join(
        f'TRY_CAST("{k}" AS {type_map.get(v, "VARCHAR")}) AS "{k}"'
        for k, v in fields.items()
    )
    columns_str = ", ".join(
        f"'{k}': '{type_map.get(v, 'VARCHAR')}'" for k, v in fields.items()
    )

    con.execute(f"DROP TABLE IF EXISTS {table_name}")
    con.execute(f"""
        CREATE TABLE {table_name} AS 
        SELECT {cast_sql}
        FROM read_csv('{usv_path}', 
            delim='\x1f', 
            header=False, 
            auto_detect=False,
            columns={{{columns_str}}},
            quote='', 
            escape='', 
            null_padding=True,
            ignore_errors=True)
    """)


def _load_gm_list_results_auto(
    con: duckdb.DuckDBPyConnection, results_dir: Path
) -> None:
    """Load GmListResult files with auto-detected schema.

    GmListResult USVs use:
    - 0x1f (US) as field separator
    - 0x1e (RS) or 0x0a (LF) as record separator

    We preprocess files using normalize_usv_record_separators so DuckDB can parse them.
    """
    import tempfile

    from cocli.utils.usv_utils import normalize_usv_record_separators

    sep = "\x1f"

    con.execute("DROP TABLE IF EXISTS gm_results")

    combined_content = ""
    for usv_file in results_dir.rglob("*.usv"):
        with open(usv_file, "rb") as f:
            combined_content += normalize_usv_record_separators(f.read())

    if not combined_content.strip():
        con.execute("CREATE TABLE gm_results AS SELECT NULL AS place_id WHERE FALSE")
        return

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as tmp:
        tmp.write(combined_content)
        temp_path = tmp.name

    try:
        con.execute(f"""
            CREATE TABLE gm_results AS
            SELECT
                NULLIF(column0, '')::VARCHAR AS place_id,
                NULLIF(column1, '')::VARCHAR AS company_slug,
                NULLIF(column2, '')::VARCHAR AS name,
                NULLIF(column3, '')::VARCHAR AS phone,
                NULLIF(column4, '')::VARCHAR AS domain,
                TRY_CAST(NULLIF(column5, '') AS BIGINT) AS reviews_count,
                TRY_CAST(NULLIF(column6, '') AS DOUBLE) AS average_rating,
                NULLIF(column7, '')::VARCHAR AS street_address,
                NULLIF(column8, '')::VARCHAR AS gmb_url,
                NULLIF(column9, '')::VARCHAR AS discovery_phrase,
                NULLIF(column10, '')::VARCHAR AS discovery_tile_id,
                NULLIF(column11, '')::VARCHAR AS html
            FROM read_csv('{temp_path}',
                delim='{sep}',
                header=False,
                auto_detect=False,
                columns={{
                    'column0': 'VARCHAR',
                    'column1': 'VARCHAR',
                    'column2': 'VARCHAR',
                    'column3': 'VARCHAR',
                    'column4': 'VARCHAR',
                    'column5': 'VARCHAR',
                    'column6': 'VARCHAR',
                    'column7': 'VARCHAR',
                    'column8': 'VARCHAR',
                    'column9': 'VARCHAR',
                    'column10': 'VARCHAR',
                    'column11': 'VARCHAR'
                }},
                null_padding=True,
                ignore_errors=True)
        """)
    finally:
        Path(temp_path).unlink(missing_ok=True)
