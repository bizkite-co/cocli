# POLICY: frictionless-data-policy-enforcement (See docs/FRICTIONLESS_DATA_POLICY_ENFORCEMENT.md)
import json
import logging
from pathlib import Path
from typing import Dict, Optional
import duckdb

logger = logging.getLogger(__name__)

def get_duckdb_schema_from_datapackage(datapackage_path: Path) -> Dict[str, str]:
    """
    Parses a Frictionless Data datapackage.json and returns a dictionary 
    mapping column names to DuckDB types.
    """
    if not datapackage_path.exists():
        raise FileNotFoundError(f"Datapackage not found: {datapackage_path}")

    with open(datapackage_path, "r") as f:
        data = json.load(f)

    # We assume one resource for now
    resource = data["resources"][0]
    fields = resource["schema"]["fields"]
    
    type_map = {
        "string": "VARCHAR",
        "integer": "BIGINT",
        "number": "DOUBLE",
        "datetime": "VARCHAR", 
        "boolean": "BOOLEAN"
    }
    
    duck_cols = {}
    for field in fields:
        name = field["name"]
        orig_name = name
        # Standardizing on internal DuckDB names for join consistency
        if name == "company_slug":
            name = "slug"
        elif name == "phone":
            name = "phone_number"
        elif name == "keyword":
            name = "tags"
            
        if name != orig_name:
            logger.debug(f"FDPE: Renaming column {orig_name} -> {name}")
            
        f_type = field.get("type", "string")
        duck_cols[name] = type_map.get(f_type, "VARCHAR")
        
    return duck_cols

def load_usv_to_duckdb(con: duckdb.DuckDBPyConnection, table_name: str, usv_path: Path, datapackage_path: Optional[Path] = None) -> None:
    """
    FDPE ENFORCEMENT: Loads a headerless USV file into DuckDB using datapackage.json 
    as the authority for column names and types.
    """
    if not usv_path.exists():
        logger.warning(f"USV file not found: {usv_path}")
        return

    # 1. Determine schema from datapackage (MANDATORY for FDPE)
    columns: Dict[str, str] = {}
    if datapackage_path and datapackage_path.exists():
        try:
            columns = get_duckdb_schema_from_datapackage(datapackage_path)
        except Exception as e:
            logger.error(f"Failed to parse datapackage for {table_name}: {e}")

    try:
        con.execute(f"DROP TABLE IF EXISTS {table_name}")
        
        if columns:
            # FDPE: Use explicit column mapping for headerless file
            # Map columns to VARCHAR first to prevent early casting errors
            columns_def = ", ".join([f"'{name}': 'VARCHAR'" for name in columns.keys()])
            
            # Use TRY_CAST for type safety (Requirement 3 of FDPE)
            cast_sql = ", ".join([f"TRY_CAST(\"{name}\" AS {dtype}) as \"{name}\"" for name, dtype in columns.items()])
            
            con.execute(f"""
                CREATE TABLE {table_name} AS 
                SELECT {cast_sql} 
                FROM read_csv('{usv_path}', delim='\x1f', header=False, auto_detect=False, 
                              columns={{{columns_def}}}, quote='', escape='')
            """)
        else:
            # Fallback to auto-detection (violates strict FDPE but allows operation)
            logger.warning(f"FDPE VIOLATION: Loading {table_name} without schema.")
            con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM read_csv('{usv_path}', delim='\x1f', header=False, auto_detect=True, all_varchar=True, quote='', escape='')")
            
        count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        logger.debug(f"FDPE: Loaded {count} rows into {table_name}")

    except Exception as e:
        logger.error(f"FDPE Load failed for {table_name}: {e}")
        raise
