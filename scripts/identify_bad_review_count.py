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

# 2. Query to identify rows where reviews_count matches the area code
# Using schema field names: 'company_slug', 'reviews_count', 'phone'
# Use REGEXP_EXTRACT to robustly get the area code
query = """
    SELECT company_slug, reviews_count, phone
    FROM prospects
    WHERE CAST(reviews_count AS VARCHAR) = REGEXP_EXTRACT(phone, '^1?(\\d{3})', 1)
      AND reviews_count IS NOT NULL
"""
results = con.execute(query).fetchall()

# 3. Save to recovery file
output_path = Path("data/campaigns/roadmap/recovery/review-count-matches-area-code.usv")
with open(output_path, "w", encoding="utf-8") as f:
    writer = USVWriter(f)
    writer.writerow(["company_slug", "reviews_count", "phone"])  # Header
    for row in results:
        writer.writerow(row)

print(f"Found {len(results)} problematic records.")
print(f"Wrote report to {output_path}")
