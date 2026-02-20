import duckdb
import os
import json
from pathlib import Path
from cocli.core.paths import paths

def debug_duckdb():
    checkpoint_path = paths.campaign("roadmap").index("google_maps_prospects").checkpoint
    print(f"Checking: {checkpoint_path}")
    
    con = duckdb.connect(database=':memory:')
    
    # 1. Test pure raw load without schema first
    try:
        print("Attempting raw load (sniffing)...")
        con.execute(f"CREATE TABLE raw_check AS SELECT * FROM read_csv_auto('{checkpoint_path}', delim='\\x1f', quote='', escape='')")
        count = con.execute("SELECT count(*) FROM raw_check").fetchone()[0]
        print(f"Raw load count: {count}")
        
        if count > 0:
            cols = con.execute("DESCRIBE raw_check").fetchall()
            print(f"Detected {len(cols)} columns.")
            
    except Exception as e:
        print(f"Raw load failed: {e}")

if __name__ == "__main__":
    debug_duckdb()
