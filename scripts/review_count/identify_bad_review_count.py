import duckdb
from cocli.core.paths import paths
from cocli.utils.duckdb_utils import load_usv_to_duckdb
from cocli.utils.usv_utils import USVWriter

con = duckdb.connect(database=":memory:")

campaign_name = "roadmap"
usv_path = paths.campaign(campaign_name).index("google_maps_prospects").checkpoint
dp_path = usv_path.parent / "datapackage.json"
load_usv_to_duckdb(con, "prospects", usv_path, datapackage_path=dp_path)

# Stats
res = con.execute("SELECT COUNT(*) FROM prospects").fetchone()
total = res[0] if res else 0
res = con.execute(
    "SELECT COUNT(*) FROM prospects WHERE reviews_count IS NOT NULL"
).fetchone()
with_reviews = res[0] if res else 0
bad_query = """
    SELECT company_slug, reviews_count, phone
    FROM prospects
    WHERE CAST(reviews_count AS VARCHAR) = REGEXP_EXTRACT(phone, '^1?[^\\d]*(\\d{3})', 1)
      AND reviews_count IS NOT NULL
"""
results = con.execute(bad_query).fetchall()

recovery_dir = paths.campaign(campaign_name).path / "recovery"
recovery_dir.mkdir(parents=True, exist_ok=True)
output_path = recovery_dir / "review-count-matches-area-code.usv"

with open(output_path, "w", encoding="utf-8") as f:
    writer = USVWriter(f)
    writer.writerow(["company_slug", "reviews_count", "phone"])
    for row in results:
        writer.writerow(row)

print(f"Total records: {total}")
print(f"Records with reviews_count: {with_reviews}")
print(f"Bad records (reviews_count = area_code): {len(results)}")
print(f"Path: {output_path}")
if results:
    print("\nContent preview:")
    print(output_path.read_text(encoding="utf-8")[:500])
