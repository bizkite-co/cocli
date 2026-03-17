import duckdb
from pathlib import Path
from cocli.utils.duckdb_utils import find_datapackage, load_usv_to_duckdb

# Initialize DuckDB and load data
con = duckdb.connect(database=":memory:")
usv_path = Path(
    "data/campaigns/roadmap/indexes/google_maps_prospects/prospects.checkpoint.usv"
)
dp_path = find_datapackage(usv_path)
load_usv_to_duckdb(con, "prospects", usv_path, datapackage_path=dp_path)

# Audit phone patterns
print("--- Phone Number Format Audit ---")
patterns = con.execute("""
    SELECT 
        LENGTH(phone) as len,
        REGEXP_EXTRACT(phone, '^1?(\\d{3})', 1) as area_code,
        COUNT(*) as cnt
    FROM prospects
    WHERE phone IS NOT NULL AND phone != ''
    GROUP BY 1, 2
    ORDER BY cnt DESC
""").fetchall()

for row in patterns:
    # Check if area code was extracted
    label = "Valid Area Code" if row[1] else "No Area Code Found"
    print(f"Length {row[0]}, {label} '{row[1]}': {row[2]} records")
