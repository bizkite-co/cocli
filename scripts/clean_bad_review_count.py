import duckdb
from pathlib import Path
from cocli.utils.duckdb_utils import find_datapackage, load_usv_to_duckdb
from cocli.utils.usv_utils import USVWriter

# 1. Initialize DuckDB and load the data using the authoritative schema
con = duckdb.connect(database=":memory:")
usv_path = Path(
    "data/campaigns/roadmap/indexes/google_maps_prospects/prospects.checkpoint.usv"
)
dp_path = find_datapackage(usv_path)
load_usv_to_duckdb(con, "prospects", usv_path, datapackage_path=dp_path)

# 2. Fix the data using SQL by column name
# Update rows where reviews_count matches the area code (digits 2, 3, 4 of the phone string)
# Use REGEXP_EXTRACT for robust area code detection
con.execute("""
    UPDATE prospects 
    SET reviews_count = NULL 
    WHERE CAST(reviews_count AS VARCHAR) = REGEXP_EXTRACT(phone, '^1?(\\d{3})', 1) 
      AND reviews_count IS NOT NULL
""")

# 3. Export back to USV
# Must match the original USV format: delimiter '\x1f', no header
output_usv = Path(
    "data/campaigns/roadmap/indexes/google_maps_prospects/prospects.checkpoint.cleaned.usv"
)

# Get column names to ensure order
columns = [row[1] for row in con.execute("PRAGMA table_info(prospects)").fetchall()]

with open(output_usv, "w", encoding="utf-8") as f:
    writer = USVWriter(f)  # USVWriter uses UNIT_SEP
    # Fetch all data, selecting columns to guarantee order
    query = f"SELECT {', '.join([f'"{c}"' for c in columns])} FROM prospects"
    data = con.execute(query).fetchall()

    for row in data:
        # Trim strings
        trimmed_row = [str(cell).strip() if cell is not None else "" for cell in row]
        writer.writerow(trimmed_row)

print(f"Cleaned file written to {output_usv}")
