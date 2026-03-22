from pathlib import Path
from cocli.utils.usv_utils import USVWriter
import duckdb

# Paths
results_dir = Path(
    "/home/mstouffer/.local/share/cocli_data_dev/campaigns/roadmap/queues/gm-list/completed/results"
)
compiled_path = results_dir / "compiled.usv"
compacted_path = results_dir / "compacted.usv"

# Use DuckDB for cleaning and deduplication
con = duckdb.connect(database=":memory:")
print(f"Reading {compiled_path}...")
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

# 1. Clean misaligned review_count (Set to NULL where bad)
con.execute("""
    UPDATE raw_data
    SET reviews_count = NULL
    WHERE TRY_CAST(reviews_count AS BIGINT) IS NULL 
       OR reviews_count = REGEXP_EXTRACT(phone, '^1?[^\\d]*(\\d{3})', 1)
       OR reviews_count = REGEXP_EXTRACT(street_address, '^(\\d+)', 1)
""")

# 2. Filter invalid rows based on schema constraints
# place_id: 26-29, company_slug: 3-100, name: 1-100, phone: 10-15 (if present),
# domain: 3-100 (if present), reviews_count: >=0 (if present),
# average_rating: 0.0-5.0 (if present), street_address: 5-100 (if present), gmb_url: 20+ (if present)
con.execute("""
    CREATE TABLE compacted_table AS
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

# Export invalid rows
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
    )) TO '{results_dir / "results.invalid.usv"}' (DELIMITER '\x1f', HEADER FALSE)
""")

# 3. Dedupe on place_id (keeping the row with highest reviews_count)
# Note: we are operating on the cleaned table now
con.execute("""
    CREATE TABLE final_compacted AS
    SELECT * FROM (
        SELECT *, ROW_NUMBER() OVER (
            PARTITION BY place_id 
            ORDER BY TRY_CAST(reviews_count AS BIGINT) DESC NULLS LAST
        ) as rn
        FROM compacted_table
    ) WHERE rn = 1
""")
con.execute("ALTER TABLE final_compacted DROP rn")

# 3. Export to USV
# Need to get data out of DuckDB into a USV
records = con.execute("SELECT * FROM final_compacted").fetchall()

print(f"Compacting {len(records)} records to {compacted_path}...")
with open(compacted_path, "w", encoding="utf-8") as f_out:
    writer = USVWriter(f_out)
    for row in records:
        writer.writerow(row)
print("Compaction complete.")
