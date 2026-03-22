import duckdb
import argparse
import sys
from pathlib import Path
from cocli.core.paths import paths
from cocli.utils.duckdb_utils import load_usv_to_duckdb
from cocli.utils.usv_utils import USVWriter


def load_gm_list_results(con, usv_path):
    con.execute(f"""
        CREATE TABLE prospects AS
        SELECT
            NULLIF(column0, '')::VARCHAR AS place_id,
            NULLIF(column1, '')::VARCHAR AS company_slug,
            NULLIF(column2, '')::VARCHAR AS name,
            NULLIF(column3, '')::VARCHAR AS category,
            NULLIF(column4, '')::VARCHAR AS phone,
            NULLIF(column5, '')::VARCHAR AS domain,
            TRY_CAST(NULLIF(column6, '') AS BIGINT) AS reviews_count,
            TRY_CAST(NULLIF(column7, '') AS DOUBLE) AS average_rating,
            NULLIF(column8, '')::VARCHAR AS street_address,
            NULLIF(column9, '')::VARCHAR AS gmb_url,
            NULLIF(column10, '')::VARCHAR AS discovery_phrase,
            NULLIF(column11, '')::VARCHAR AS discovery_tile_id,
            NULLIF(column12, '')::VARCHAR AS html
        FROM read_csv('{usv_path}',
            delim='\x1f',
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
                'column11': 'VARCHAR',
                'column12': 'VARCHAR'
            }},
            null_padding=True,
            ignore_errors=True)
    """)


parser = argparse.ArgumentParser()
parser.add_argument("--input", type=Path, help="Path to input USV file")
args = parser.parse_args()

con = duckdb.connect(database=":memory:")

if args.input:
    print(f"Loading from: {args.input}")
    load_gm_list_results(con, args.input)
    campaign_name = "roadmap"  # Hardcoded assumption for now
    output_filename = "review-count-misaligned-source.usv"
else:
    campaign_name = "roadmap"
    usv_path = paths.campaign(campaign_name).index("google_maps_prospects").checkpoint
    dp_path = usv_path.parent / "datapackage.json"
    load_usv_to_duckdb(con, "prospects", usv_path, datapackage_path=dp_path)
    output_filename = "review-count-misaligned.usv"

# Stats
res = con.execute("SELECT COUNT(*) FROM prospects").fetchone()
total = res[0] if res else 0
res = con.execute(
    "SELECT COUNT(*) FROM prospects WHERE reviews_count IS NOT NULL"
).fetchone()
with_reviews = res[0] if res else 0

# Union query to find bad records based on area code OR street address number
bad_query = """
    SELECT company_slug, reviews_count, phone, street_address, 'area_code' AS match_type
    FROM prospects
    WHERE CAST(reviews_count AS VARCHAR) = REGEXP_EXTRACT(phone, '^1?[^\\d]*(\\d{3})', 1)
      AND reviews_count IS NOT NULL
    UNION ALL
    SELECT company_slug, reviews_count, phone, street_address, 'street_number' AS match_type
    FROM prospects
    WHERE CAST(reviews_count AS VARCHAR) = REGEXP_EXTRACT(street_address, '^(\\d+)', 1)
      AND reviews_count IS NOT NULL
"""
results = con.execute(bad_query).fetchall()

recovery_dir = paths.campaign(campaign_name).path / "recovery"
recovery_dir.mkdir(parents=True, exist_ok=True)
output_path = recovery_dir / output_filename

with open(output_path, "w", encoding="utf-8") as f:
    writer = USVWriter(f)
    writer.writerow(
        ["company_slug", "reviews_count", "phone", "street_address", "match_type"]
    )
    for row in results:
        writer.writerow(row)

print(f"Total records: {total}")
print(f"Records with reviews_count: {with_reviews}")
print(f"Bad records (reviews_count = area_code OR street_number): {len(results)}")
print(f"Path: {output_path}")
if results:
    print("\nContent preview:")
    print(output_path.read_text(encoding="utf-8")[:500])
