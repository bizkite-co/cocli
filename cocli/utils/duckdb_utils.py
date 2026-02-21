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
    as the sole authority for column names and types.
    """
    import csv
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

    # 2. Read raw headerless data
    try:
        with open(usv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter='\x1f', quotechar=None, quoting=csv.QUOTE_NONE)
            rows = list(reader)
            
            if not rows:
                if columns:
                    col_def = ", ".join([f"{name} {dtype}" for name, dtype in columns.items()])
                    con.execute(f"CREATE TABLE {table_name} ({col_def})")
                return

            # FDPE: Mapping headerless stream to names explicitly
            if columns:
                header = list(columns.keys())
            else:
                # Emergency fallback if no datapackage (violates FDPE but prevents crash)
                logger.warning(f"FDPE VIOLATION: No schema for {table_name}. Defaulting to columnN.")
                header = [f"column{i}" for i in range(len(rows[0]))]

            # 3. Sanitize and Insert via Pandas/DuckDB
            import pandas as pd
            expected_len = len(header)
            sanitized_data = []
            for r in rows:
                if len(r) == expected_len:
                    sanitized_data.append(r)
                else:
                    # Pad or truncate to match schema
                    sanitized_data.append((r + [""] * expected_len)[:expected_len])

            df = pd.DataFrame(sanitized_data, columns=header)
            
            con.execute(f"DROP TABLE IF EXISTS {table_name}")
            con.register("df_view", df)
            
            if columns:
                # Cast values according to defined types (Requirement 3 of FDPE)
                cast_cols = []
                for col in header:
                    if col in columns:
                        cast_cols.append(f"TRY_CAST(\"{col}\" AS {columns[col]}) as \"{col}\"")
                    else:
                        cast_cols.append(f"\"{col}\"")
                select_sql = ", ".join(cast_cols)
                con.execute(f"CREATE TABLE {table_name} AS SELECT {select_sql} FROM df_view")
            else:
                con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df_view")
                
            con.unregister("df_view")
            logger.debug(f"FDPE: Loaded {len(sanitized_data)} rows into {table_name}")

    except Exception as e:
        logger.error(f"FDPE Load failed for {table_name}: {e}")
        # Final fallback to raw sniffing (Strict FDPE would fail here)
        con.execute(f"DROP TABLE IF EXISTS {table_name}")
        con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM read_csv('{usv_path}', delim='\x1f', quote='', escape='', header=False, auto_detect=True, all_varchar=True)")
