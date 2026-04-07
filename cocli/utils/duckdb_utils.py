# POLICY: frictionless-data-policy-enforcement (See docs/FRICTIONLESS_DATA_POLICY_ENFORCEMENT.md)
import fnmatch
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Set
import duckdb

logger = logging.getLogger(__name__)


def get_schema_field_names(
    datapackage_path: Path, resource_name: Optional[str] = None
) -> List[str]:
    """
    Returns list of field names from a datapackage's schema.
    """
    if not datapackage_path.exists():
        return []

    with open(datapackage_path, "r") as f:
        data = json.load(f)

    resource = None
    if resource_name:
        for r in data.get("resources", []):
            if r.get("name") == resource_name:
                resource = r
                break

    if not resource:
        resource = data["resources"][0]

    fields = resource.get("schema", {}).get("fields", [])
    return [f["name"] for f in fields]


def normalize_column_names(columns_str: str, valid_columns: List[str]) -> str:
    """
    Normalizes a comma-separated list of column names, replacing known aliases.

    Known aliases:
    - company_slug -> slug
    - reviews -> reviews_count
    - rating -> average_rating

    Also removes invalid columns and warns about them.
    """
    if not columns_str.strip():
        return "*"

    valid_set: Set[str] = set(valid_columns)
    aliases = {
        "company_slug": "slug",
        "reviews": "reviews_count",
        "rating": "average_rating",
    }

    cols = [c.strip() for c in columns_str.split(",")]
    normalized = []
    removed = []

    for col in cols:
        # Check aliases
        if col in aliases:
            col = aliases[col]

        if col == "*":
            normalized.append("*")
        elif col in valid_set:
            normalized.append(col)
        else:
            removed.append(col)

    if removed:
        logger.warning(f"Unknown columns removed from query: {removed}")

    return ", ".join(normalized) if normalized else "*"


def extract_columns_from_query(query: str) -> Set[str]:
    """
    Extracts column references from a SQL WHERE clause.
    Handles: column_name, table.column_name, "column name"
    """
    # Match column references: word chars, or quoted identifiers
    # This is a simplified extraction - won't catch all cases
    pattern = r'(?:WHERE|AND|OR)\s+("?[\w]+"?)\s*(?:=|>|<|LIKE|IN|IS|BETWEEN)'
    matches = re.findall(pattern, query, re.IGNORECASE)

    # Filter out SQL keywords
    sql_keywords = {"WHERE", "AND", "OR", "NULL", "NOT", "IN", "BETWEEN", "LIKE"}
    return {m for m in matches if m.upper() not in sql_keywords and m != "*"}


def validate_query_columns(query: str, valid_columns: List[str]) -> List[str]:
    """
    Validates that all column references in a query exist in the schema.
    Returns list of unknown/invalid columns.
    """
    used_cols = extract_columns_from_query(query)
    valid_set = set(valid_columns)

    # Also check aliases
    aliases = {"company_slug", "reviews", "rating"}
    all_valid = valid_set | aliases

    return [col for col in used_cols if col not in all_valid]


def match_resource_path(filename: str, res_path: str) -> bool:
    """Matches a filename against a resource path (supporting glob patterns)."""
    if res_path == filename:
        return True
    # Strip **/ from glob patterns for fnmatch
    pattern = res_path.replace("**/", "")
    return fnmatch.fnmatch(filename, pattern)


def find_datapackage(file_path: Path) -> Optional[Path]:
    """
    DISCOVERY: Navigates up the directory tree to find the authoritative
    datapackage.json that manages the given file.

    The datapackage must contain a resource whose 'path' matches the filename
    or a glob pattern.

    If the input is already a datapackage.json, returns it directly.
    """
    # If already a datapackage.json, return it
    if file_path.name == "datapackage.json":
        return file_path if file_path.exists() else None

    current_dir = file_path.parent
    filename = file_path.name

    # Safety: Don't traverse beyond the project or system root
    while current_dir and current_dir != current_dir.parent:
        dp_path = current_dir / "datapackage.json"
        if dp_path.exists():
            try:
                with open(dp_path, "r") as f:
                    pkg = json.load(f)
                    resources = pkg.get("resources", [])
                    for res in resources:
                        res_path = res.get("path")
                        if match_resource_path(filename, res_path):
                            logger.debug(
                                f"FDPE: Found matching datapackage for {filename} at {dp_path}"
                            )
                            return dp_path
            except Exception as e:
                logger.warning(
                    f"FDPE: Error reading potential datapackage at {dp_path}: {e}"
                )

        # Stop if we hit a known root boundary
        if (current_dir / ".git").exists():
            break

        current_dir = current_dir.parent

    return None


def get_duckdb_schema_from_datapackage(
    datapackage_path: Path, resource_name: Optional[str] = None
) -> Dict[str, str]:
    """
    Parses a Frictionless Data datapackage.json and returns a dictionary
    mapping column names to DuckDB types.
    """
    if not datapackage_path.exists():
        raise FileNotFoundError(f"Datapackage not found: {datapackage_path}")

    with open(datapackage_path, "r") as f:
        data = json.load(f)

    # Find the right resource
    resource = None
    if resource_name:
        for r in data.get("resources", []):
            if r.get("name") == resource_name:
                resource = r
                break

    if not resource:
        resource = data["resources"][0]

    fields = resource["schema"]["fields"]

    type_map = {
        "string": "VARCHAR",
        "integer": "BIGINT",
        "number": "DOUBLE",
        "datetime": "VARCHAR",
        "boolean": "BOOLEAN",
    }

    duck_cols = {}
    for field in fields:
        name = field["name"]
        f_type = field.get("type", "string")
        duck_cols[name] = type_map.get(f_type, "VARCHAR")

    return duck_cols


def load_usv_to_duckdb(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
    usv_path: Path,
    datapackage_path: Optional[Path] = None,
) -> None:
    """
    FDPE ENFORCEMENT: Loads a headerless USV file into DuckDB using a
    datapackage.json (discovered or provided) as the authority.
    """
    # 1. Discover datapackage if not provided
    dp_path = datapackage_path or find_datapackage(usv_path)

    columns: Dict[str, str] = {}
    if dp_path and dp_path.exists():
        try:
            # Note: We use the filename as the resource hint
            columns = get_duckdb_schema_from_datapackage(dp_path)
        except Exception as e:
            logger.error(f"Failed to parse datapackage for {table_name}: {e}")

    try:
        con.execute(f"DROP TABLE IF EXISTS {table_name}")

        # Check if file exists and is a regular file (not /dev/null)
        if not usv_path.exists() or not usv_path.is_file():
            logger.debug(
                f"USV file not found or special: {usv_path}. Creating empty table."
            )
            if columns:
                cols_sql = ", ".join(
                    [f'"{name}" {dtype}' for name, dtype in columns.items()]
                )
                con.execute(f"CREATE TABLE {table_name} ({cols_sql})")
            else:
                # Robust fallback for map-based tables
                con.execute(f"""
                    CREATE TABLE {table_name} (
                        place_id VARCHAR, slug VARCHAR, name VARCHAR, phone VARCHAR,
                        created_at VARCHAR, updated_at VARCHAR, version BIGINT, processed_by VARCHAR,
                        company_hash VARCHAR, keyword VARCHAR, full_address VARCHAR, street_address VARCHAR,
                        city VARCHAR, zip VARCHAR, municipality VARCHAR, state VARCHAR, country VARCHAR,
                        timezone VARCHAR, phone_standard_format VARCHAR, website VARCHAR, domain VARCHAR,
                        first_category VARCHAR, second_category VARCHAR, claimed_google_my_business VARCHAR,
                        reviews_count BIGINT, average_rating DOUBLE, hours VARCHAR, saturday VARCHAR,
                        sunday VARCHAR, monday VARCHAR, tuesday VARCHAR, wednesday VARCHAR, thursday VARCHAR,
                        friday VARCHAR, latitude DOUBLE, longitude DOUBLE, coordinates VARCHAR, plus_code VARCHAR,
                        menu_link VARCHAR, gmb_url VARCHAR, cid VARCHAR, google_knowledge_url VARCHAR,
                        kgmid VARCHAR, image_url VARCHAR, favicon VARCHAR, review_url VARCHAR,
                        facebook_url VARCHAR, linkedin_url VARCHAR, instagram_url VARCHAR, thumbnail_url VARCHAR,
                        reviews VARCHAR, quotes VARCHAR, uuid VARCHAR, discovery_phrase VARCHAR,
                        discovery_tile_id VARCHAR, email VARCHAR, type VARCHAR, display VARCHAR
                    )
                """)
            return

        if columns:
            columns_def = ", ".join(
                [f"\"{name}\": '{dtype}'" for name, dtype in columns.items()]
            )
            cast_sql = ", ".join(
                [
                    f'TRY_CAST("{name}" AS {dtype}) as "{name}"'
                    for name, dtype in columns.items()
                ]
            )

            con.execute(f"""
                CREATE TABLE {table_name} AS 
                SELECT {cast_sql} 
                FROM read_csv('{usv_path}', delim='\x1f', header=False, auto_detect=False, 
                              columns={{{columns_def}}}, quote='', escape='', 
                              null_padding=True)
            """)
        else:
            # Fallback to auto-detection (violates strict FDPE but allows operation)
            logger.warning(f"FDPE VIOLATION: Loading {table_name} without schema.")
            con.execute(
                f"CREATE TABLE {table_name} AS SELECT * FROM read_csv('{usv_path}', delim='\x1f', header=False, auto_detect=True, all_varchar=True, quote='', escape='')"
            )

        res = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        count = res[0] if res else 0
        logger.debug(f"FDPE: Loaded {count} rows into {table_name}")

    except Exception as e:
        logger.error(f"FDPE Load failed for {table_name}: {e}")
        raise


def load_from_datapackage(
    con: duckdb.DuckDBPyConnection, table_name: str, datapackage_path: Path
) -> None:
    """
    Loads all USV files matched by a datapackage's glob patterns into a unified table.
    """
    if not datapackage_path.exists():
        raise FileNotFoundError(f"Datapackage not found: {datapackage_path}")

    with open(datapackage_path, "r") as f:
        data = json.load(f)

    base_dir = datapackage_path.parent

    # 1. Create target table schema based on datapackage (assuming first resource is authoritative)
    columns = get_duckdb_schema_from_datapackage(datapackage_path)
    cols_sql = ", ".join([f'"{name}" {dtype}' for name, dtype in columns.items()])
    con.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({cols_sql})")

    # 2. Load each resource
    for res in data.get("resources", []):
        res_path_pattern = res.get("path")
        # Find all files matching the glob pattern
        usv_files = list(base_dir.glob(res_path_pattern))

        # Load each file
        for usv_path in usv_files:
            # Load into a temporary table and insert into the unified table
            temp_table = f"temp_{usv_path.stem.replace('-', '_')}"
            load_usv_to_duckdb(con, temp_table, usv_path, datapackage_path)
            con.execute(f"INSERT INTO {table_name} SELECT * FROM {temp_table}")
            con.execute(f"DROP TABLE {temp_table}")
