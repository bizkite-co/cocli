import os
import sys
import logging
import duckdb
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.models.google_maps_prospect import GoogleMapsProspect

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def consolidate(campaign_name: str) -> None:
    data_home = Path(os.environ.get("COCLI_DATA_HOME", Path.home() / ".local/share/cocli_data"))
    recovery_dir = data_home / "campaigns" / campaign_name / "recovery" / "indexes" / "google_maps_prospects"
    wal_dir = recovery_dir / "wal"
    checkpoint_path = recovery_dir / "prospects.checkpoint.usv"
    
    if not wal_dir.exists():
        logger.error(f"WAL directory not found: {wal_dir}")
        return

    logger.info(f"Consolidating recovery index for {campaign_name}...")
    logger.info(f"Source: {wal_dir}")
    logger.info(f"Target: {checkpoint_path}")

    # 1. Collect all WAL files
    wal_files = list(wal_dir.rglob("*.usv"))
    if not wal_files:
        logger.info("No WAL files found to consolidate.")
        return
    
    logger.info(f"Found {len(wal_files)} WAL files.")

    # 2. Setup DuckDB
    con = duckdb.connect(database=':memory:')
    con.execute("SET memory_limit='4GB'")
    con.execute("SET preserve_insertion_order=false")
    con.execute("SET threads=2")
    
    # Define schema based on GoogleMapsProspect
    # We use VARCHAR for everything to ensure reliable ingest
    column_names = list(GoogleMapsProspect.model_fields.keys())
    
    # 3. Load files into a temporary table
    wal_glob = str(wal_dir / "**" / "*.usv")
    
    try:
        # Construct the columns dict for read_csv
        cols_dict = ", ".join([f"'{name}': 'VARCHAR'" for name in column_names])
        
        con.execute(f"""
            CREATE TABLE all_records AS 
            SELECT * FROM read_csv('{wal_glob}', 
                delim='\x1f', 
                header=False, 
                columns={{ {cols_dict} }},
                ignore_errors=True
            )
        """)
        
        # Debug: Print columns
        columns = con.execute("PRAGMA table_info('all_records')").fetchall()
        logger.info(f"Detected columns: {[c[1] for c in columns]}")
        
        res = con.execute("SELECT count(*) FROM all_records").fetchone()
        count = res[0] if res else 0
        logger.info(f"Loaded {count} total records from WAL.")

        # 4. Deduplicate: Take the latest record for each place_id
        # We use the index of the columns if names are still failing, 
        # but let's try the names first now that we simplified.
        con.execute("""
            CREATE TABLE deduped AS
            SELECT * FROM all_records
            QUALIFY ROW_NUMBER() OVER(PARTITION BY place_id ORDER BY updated_at DESC, created_at DESC) = 1
        """)
        
        res_deduped = con.execute("SELECT count(*) FROM deduped").fetchone()
        final_count = res_deduped[0] if res_deduped else 0
        logger.info(f"Deduplicated to {final_count} unique records.")

        # 5. Export to checkpoint
        con.execute(f"""
            COPY deduped TO '{checkpoint_path}' (DELIMITER '\x1f', HEADER FALSE)
        """)
        
        logger.info(f"Successfully created checkpoint with {final_count} records.")
        
    except Exception as e:
        logger.error(f"Consolidation failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    campaign = "turboship"
    if len(sys.argv) > 1:
        campaign = sys.argv[1]
    consolidate(campaign)
