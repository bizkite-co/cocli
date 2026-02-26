# POLICY: frictionless-data-policy-enforcement
import duckdb
import logging
import json
from cocli.core.paths import paths
from cocli.utils.duckdb_utils import load_usv_to_duckdb

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("debug_duckdb")

def debug_duckdb_mapping() -> None:
    campaign = "roadmap"
    logger.info(f"--- Debugging DuckDB Schema & Mapping for: {campaign} ---")

    con = duckdb.connect(database=':memory:')
    
    # Target Index
    prospect_idx = paths.campaign(campaign).index("google_maps_prospects")
    checkpoint_path = prospect_idx.checkpoint
    prospect_dp = prospect_idx.path / "datapackage.json"

    if not checkpoint_path.exists():
        logger.error(f"Checkpoint not found: {checkpoint_path}")
        return

    # 1. Load using the actual utility
    logger.info(f"Loading {checkpoint_path.name} into DuckDB...")
    try:
        load_usv_to_duckdb(con, "items_checkpoint", checkpoint_path, prospect_dp)
    except Exception as e:
        logger.error(f"load_usv_to_duckdb failed: {e}")
        return

    # 2. Check Table Info
    logger.info("\n--- Table Info: items_checkpoint ---")
    res = con.execute("PRAGMA table_info('items_checkpoint')").fetchall()
    for col in res:
        logger.info(f"Col #{col[0]}: {col[1]} | Type: {col[2]}")

    # 3. Check Column Counts vs Datapackage
    with open(prospect_dp, "r") as f:
        dp_data = json.load(f)
        dp_fields = dp_data["resources"][0]["schema"]["fields"]
        logger.info(f"\nDatapackage Fields: {len(dp_fields)}")

    # 4. Sample data to check alignment
    logger.info("\n--- Sample Record (Top of items_checkpoint) ---")
    try:
        sample = con.execute("SELECT * FROM items_checkpoint LIMIT 1").fetchone()
        if sample:
            col_names = [desc[0] for desc in con.description]
            for i, (name, val) in enumerate(zip(col_names, sample)):
                logger.info(f"[{i:02d}] {name}: {val}")
        else:
            logger.info("No records in items_checkpoint")
    except Exception as e:
        logger.error(f"Error sampling items_checkpoint: {e}")

    # 5. Check specific problematic lead from earlier
    logger.info("\n--- Specific Lead Check: 1-tax-diva ---")
    try:
        # Note: load_usv_to_duckdb renames place_id to 'place_id' unless it found 'company_slug' and renamed it 'slug'
        # Let's check what the columns actually are
        sample = con.execute("SELECT * FROM items_checkpoint WHERE slug = '1-tax-diva'").fetchone()
        if not sample:
             # Try searching by name if slug is null/wrong
             sample = con.execute("SELECT * FROM items_checkpoint WHERE name LIKE '%Tax Diva%'").fetchone()
             
        if sample:
            col_names = [desc[0] for desc in con.description]
            for i, (name, val) in enumerate(zip(col_names, sample)):
                if val:
                    logger.info(f"[{i:02d}] {name}: {val}")
        else:
            logger.info("1-tax-diva not found in checkpoint.")
    except Exception as e:
        logger.error(f"Error searching for specific lead: {e}")

if __name__ == "__main__":
    debug_duckdb_mapping()
