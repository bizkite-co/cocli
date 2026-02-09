import duckdb
from pathlib import Path

def query_tiered_index(index_dir: Path):
    con = duckdb.connect(database=':memory:')
    
    # Define the FULL schema (55 columns)
    fields = [
        "place_id", "company_slug", "name", "phone_1", "created_at", "updated_at",
        "version", "keyword", "full_address", "street_address", "city", "zip",
        "municipality", "state", "country", "timezone", "phone_standard_format",
        "website", "domain", "first_category", "second_category", "claimed_google_my_business",
        "reviews_count", "average_rating", "hours", "saturday", "sunday", "monday",
        "tuesday", "wednesday", "thursday", "friday", "latitude", "longitude",
        "coordinates", "plus_code", "menu_link", "gmb_url", "cid", "google_knowledge_url",
        "kgmid", "image_url", "favicon", "review_url", "facebook_url", "linkedin_url",
        "instagram_url", "thumbnail_url", "reviews", "quotes", "uuid", "company_hash",
        "discovery_phrase", "discovery_tile_id", "processed_by"
    ]
    col_def = {f: 'VARCHAR' for f in fields}

    # 1. Load Checkpoint
    checkpoint_path = index_dir / "prospects.checkpoint.usv"
    con.execute(f"""
        CREATE TABLE checkpoint AS 
        SELECT * FROM read_csv('{checkpoint_path}', 
            delim='\x1f', 
            header=False, 
            columns={col_def},
            auto_detect=False,
            null_padding=True
        )
    """)
    print("Loaded Checkpoint.")

    # 2. Load WAL (Headerless)
    wal_glob = str(index_dir / "wal/*/*.usv")
    try:
        con.execute(f"""
            CREATE TABLE wal AS 
            SELECT * FROM read_csv('{wal_glob}', 
                delim='\x1f', 
                header=False, 
                columns={col_def},
                auto_detect=False,
                null_padding=True
            )
        """)
        print("Loaded WAL.")
    except Exception as e:
        print(f"WAL Load failed: {e}")
        # Create empty table if WAL fails
        con.execute("CREATE TABLE wal AS SELECT * FROM checkpoint WHERE 1=0")

    # 3. Unified View (Latest Wins)
    con.execute("""
        CREATE VIEW prospects AS
        SELECT * FROM (
            SELECT *, 1 as tier FROM wal
            UNION ALL
            SELECT *, 2 as tier FROM checkpoint
        ) 
        QUALIFY ROW_NUMBER() OVER (PARTITION BY place_id ORDER BY tier ASC) = 1
    """)
    
    res = con.execute("SELECT count(*) FROM prospects").fetchone()
    print(f"Total Unified Prospects: {res[0]}")
    
    wal_hits = con.execute("SELECT count(*) FROM prospects WHERE tier = 1").fetchone()
    print(f"Updated by WAL: {wal_hits[0]}")

if __name__ == "__main__":
    idx = Path("data/campaigns/roadmap/indexes/google_maps_prospects")
    if idx.exists():
        query_tiered_index(idx)