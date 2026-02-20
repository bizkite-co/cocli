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
        # Standardizing on internal DuckDB names
        if name == "company_slug":
            name = "slug"
        elif name == "phone":
            name = "phone_number"
        elif name == "keyword":
            name = "tags"
            
        f_type = field.get("type", "string")
        duck_cols[name] = type_map.get(f_type, "VARCHAR")
        
    return duck_cols

def load_usv_to_duckdb(con: duckdb.DuckDBPyConnection, table_name: str, usv_path: Path, datapackage_path: Optional[Path] = None) -> None:
    """
    Robustly loads a USV file into a DuckDB table using Python's csv module
    as a middle-man to avoid DuckDB's sniffing issues with \x1f.
    """
    import csv
    if not usv_path.exists():
        logger.warning(f"USV file not found: {usv_path}")
        return

    # 1. Determine schema and dialect
    columns = {}
    has_header = False
    if datapackage_path and datapackage_path.exists():
        try:
            columns = get_duckdb_schema_from_datapackage(datapackage_path)
            with open(datapackage_path, "r") as f:
                dp_data = json.load(f)
                has_header = dp_data["resources"][0].get("dialect", {}).get("header", False)
        except Exception as e:
            logger.error(f"Failed to parse datapackage: {e}")

    # 2. Read the file using Python's csv module
    try:
        with open(usv_path, 'r', newline='', encoding='utf-8') as f:
            # \x1f is our standard USV delimiter
            reader = csv.reader(f, delimiter='\x1f', quotechar=None, quoting=csv.QUOTE_NONE)
            
            rows = list(reader)
            if not rows:
                # Create empty table with schema if possible
                if columns:
                    col_def = ", ".join([f"{name} {dtype}" for name, dtype in columns.items()])
                    con.execute(f"CREATE TABLE {table_name} ({col_def})")
                else:
                    con.execute(f"CREATE TABLE {table_name} (dummy VARCHAR)")
                return

            if has_header:
                header = rows[0]
                data = rows[1:]
            else:
                # If no header, we use columns from datapackage as names
                # or default to column0, column1...
                if columns:
                    header = list(columns.keys())
                else:
                    header = [f"column{i}" for i in range(len(rows[0]))]
                data = rows

            # Ensure all rows have same length as header
            expected_len = len(header)
            sanitized_data = []
            for r in data:
                if len(r) == expected_len:
                    sanitized_data.append(r)
                else:
                    # Pad or truncate
                    new_r = (r + [""] * expected_len)[:expected_len]
                    sanitized_data.append(new_r)

            # 3. Create table and insert data
            # Standard way to load from Python list of tuples/lists into DuckDB
            # We'll use a temporary view or register the data
            import pandas as pd
            df = pd.DataFrame(sanitized_data, columns=header)
            
            con.execute(f"DROP TABLE IF EXISTS {table_name}")
            con.register("df_view", df)
            
            if columns:
                # Build casting SQL
                cast_cols = []
                for col in header:
                    if col in columns:
                        # Use TRY_CAST to handle empty strings or malformed data in numeric columns
                        cast_cols.append(f"TRY_CAST({col} AS {columns[col]}) as {col}")
                    else:
                        cast_cols.append(col)
                select_sql = ", ".join(cast_cols)
                con.execute(f"CREATE TABLE {table_name} AS SELECT {select_sql} FROM df_view")
            else:
                con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df_view")
                
            con.unregister("df_view")
            
            count = len(sanitized_data)
            logger.debug(f"Loaded {count} rows into {table_name} via Pandas")

    except Exception as e:
        logger.error(f"Failed to load {table_name} via Python/Pandas: {e}")
        # Last resort fallback to raw read_csv if Pandas failed
        try:
            con.execute(f"DROP TABLE IF EXISTS {table_name}")
            con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM read_csv('{usv_path}', delim='\x1f', quote='', escape='', header={str(has_header).lower()}, auto_detect=True, all_varchar=True)")
        except Exception as e2:
            logger.error(f"Final fallback failed for {table_name}: {e2}")
