import duckdb
from cocli.core.paths import paths

def debug_duckdb() -> None:
    checkpoint_path = paths.campaign("roadmap").index("google_maps_prospects").checkpoint
    print(f"Checking: {checkpoint_path}")
    
    con = duckdb.connect(database=':memory:')
    
    # Test different quote settings
    for q in ['"', ""]:
        print(f"\n--- Testing with quote='{q}' ---")
        try:
            con.execute("DROP TABLE IF EXISTS test_load")
            # We skip column mapping for simple count test
            con.execute(f"CREATE TABLE test_load AS SELECT * FROM read_csv_auto('{checkpoint_path}', delim='\\x1f', header=False, quote='{q}', escape='{q}')")
            res = con.execute("SELECT count(*) FROM test_load").fetchone()
            count = res[0] if res else 0
            print(f"Loaded {count} rows.")
            if count > 0:
                row = con.execute("SELECT * FROM test_load LIMIT 1").fetchone()
                print("First row:", row[0] if row else "None")
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    debug_duckdb()
