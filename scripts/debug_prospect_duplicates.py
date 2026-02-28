# POLICY: frictionless-data-policy-enforcement
import duckdb
import logging
from cocli.core.paths import paths

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("debug_dupes")

def check_duplicates(campaign_name: str):
    checkpoint_path = paths.campaign(campaign_name).index("google_maps_prospects").checkpoint
    if not checkpoint_path.exists():
        logger.error(f"Checkpoint not found: {checkpoint_path}")
        return

    logger.info(f"Analyzing duplicates in: {checkpoint_path}")
    con = duckdb.connect(database=':memory:')
    
    try:
        # Use \x1f as delimiter
        # column00 is place_id, column01 is slug, column02 is name, column05 is updated_at
        query = f"""
            SELECT 
                column00 as place_id, 
                COUNT(*) as occurrences,
                MIN(column05) as oldest,
                MAX(column05) as newest
            FROM read_csv('{checkpoint_path}', delim='\x1f', header=False, auto_detect=True, all_varchar=True)
            GROUP BY column00
            HAVING occurrences > 1
            ORDER BY occurrences DESC
            LIMIT 20
        """
        results = con.execute(query).fetchall()
        
        if not results:
            logger.info("No duplicates found by place_id.")
            return

        logger.info(f"Found {len(results)} groups of duplicates (Top 20 shown):")
        logger.info(f"{'Place ID':<30} | {'Count':<5} | {'Newest Timestamp'}")
        logger.info("-" * 65)
        for r in results:
            logger.info(f"{r[0]:<30} | {r[1]:<5} | {r[3]}")

        # Total counts
        total_q = f"SELECT COUNT(*) FROM read_csv('{checkpoint_path}', delim='\x1f', header=False, all_varchar=True)"
        unique_q = f"SELECT COUNT(DISTINCT column00) FROM read_csv('{checkpoint_path}', delim='\x1f', header=False, all_varchar=True)"
        
        total = con.execute(total_q).fetchone()[0]
        unique = con.execute(unique_q).fetchone()[0]
        
        logger.info("-" * 65)
        logger.info(f"Total Rows: {total}")
        logger.info(f"Unique Place IDs: {unique}")
        logger.info(f"Bloat Factor: {((total - unique) / total * 100):.1f}%")

    except Exception as e:
        logger.error(f"DuckDB Analysis failed: {e}")

if __name__ == "__main__":
    import sys
    campaign = sys.argv[1] if len(sys.argv) > 1 else "roadmap"
    check_duplicates(campaign)
