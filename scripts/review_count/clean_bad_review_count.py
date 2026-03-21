import duckdb
from cocli.core.paths import paths
from cocli.utils.duckdb_utils import load_usv_to_duckdb
from cocli.utils.usv_utils import USVWriter

con = duckdb.connect(database=":memory:")

campaign_name = "roadmap"
usv_path = paths.campaign(campaign_name).index("google_maps_prospects").checkpoint
dp_path = usv_path.parent / "datapackage.json"
load_usv_to_duckdb(con, "prospects", usv_path, datapackage_path=dp_path)

# Count affected rows before update
res = con.execute("""
    SELECT COUNT(*) FROM prospects
    WHERE (CAST(reviews_count AS VARCHAR) = REGEXP_EXTRACT(phone, '^1?[^\\d]*(\\d{3})', 1)
           OR CAST(reviews_count AS VARCHAR) = REGEXP_EXTRACT(street_address, '^(\\d+)', 1))
      AND reviews_count IS NOT NULL
""").fetchone()
cleaned_count = res[0] if res else 0

# Update
con.execute("""
    UPDATE prospects 
    SET reviews_count = NULL 
    WHERE (CAST(reviews_count AS VARCHAR) = REGEXP_EXTRACT(phone, '^1?[^\\d]*(\\d{3})', 1)
           OR CAST(reviews_count AS VARCHAR) = REGEXP_EXTRACT(street_address, '^(\\d+)', 1))
      AND reviews_count IS NOT NULL
""")

print(f"Cleaned {cleaned_count} records.")

# Export
output_usv = usv_path.parent / "prospects.checkpoint.cleaned.usv"

columns = [row[1] for row in con.execute("PRAGMA table_info('prospects')").fetchall()]

with open(output_usv, "w", encoding="utf-8") as f:
    writer = USVWriter(f)
    query = "SELECT " + ", ".join([f'"{c}"' for c in columns]) + " FROM prospects"
    data = con.execute(query).fetchall()

    for row in data:
        trimmed_row = [str(cell).strip() if cell is not None else "" for cell in row]
        writer.writerow(trimmed_row)

print(f"Cleaned file written to {output_usv}")
