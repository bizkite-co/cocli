# POLICY: frictionless-data-policy-enforcement
import duckdb
import logging
from cocli.core.paths import paths
from cocli.utils.duckdb_utils import load_usv_to_duckdb

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("evaluate_batch")

def evaluate_batch(campaign_name: str, target_file_name: str = "recovery_targets.txt") -> None:
    idx_paths = paths.campaign(campaign_name).index("google_maps_prospects")
    checkpoint_path = idx_paths.checkpoint
    datapackage_path = idx_paths.path / "datapackage.json"
    batch_file = paths.campaign(campaign_name).path / "recovery" / target_file_name

    if not checkpoint_path.exists() or not batch_file.exists():
        logger.error("Checkpoint or Target file missing.")
        return

    logger.info(f"Evaluating {target_file_name} against clean index...")
    con = duckdb.connect(database=':memory:')
    
    try:
        # 1. Load targets (Format: pid|slug|name|url)
        con.execute(f"""
            CREATE TABLE targets AS 
            SELECT column0 as place_id 
            FROM read_csv('{batch_file}', sep='|', header=False, auto_detect=True, all_varchar=True, ignore_errors=True)
        """)

        # 2. Load Checkpoint via FDPE schema
        load_usv_to_duckdb(con, "checkpoint", checkpoint_path, datapackage_path)
        
        # 3. Join and Analyze
        # Use model-defined names: place_id, average_rating, reviews_count
        query = """
            SELECT 
                COUNT(*) as total_targeted,
                COUNT(c.average_rating) FILTER (WHERE c.average_rating IS NOT NULL AND CAST(c.average_rating AS VARCHAR) != '') as with_rating,
                COUNT(c.reviews_count) FILTER (WHERE c.reviews_count IS NOT NULL AND CAST(c.reviews_count AS VARCHAR) != '') as with_reviews,
                COUNT(*) FILTER (WHERE (c.average_rating IS NOT NULL AND CAST(c.average_rating AS VARCHAR) != '') 
                                 AND (c.reviews_count IS NOT NULL AND CAST(c.reviews_count AS VARCHAR) != '')) as with_both
            FROM targets t
            LEFT JOIN checkpoint c ON t.place_id = c.place_id
        """
        
        res = con.execute(query).fetchone()
        if not res:
            logger.error("Analysis returned no results.")
            return

        total, ratings, reviews, both = res
        
        print("\n--- RECOVERY BATCH EVALUATION ---")
        print(f"Target List:         {target_file_name}")
        print(f"Total Targeted:      {total}")
        print("-" * 30)
        print(f"With Rating:         {ratings} ({ratings*100/max(1,total):.1f}%)")
        print(f"With Review Count:   {reviews} ({reviews*100/max(1,total):.1f}%)")
        print(f"With BOTH:           {both} ({both*100/max(1,total):.1f}%)")
        print("-" * 30)
        
        if both / max(1,total) >= 0.6:
            print("✅ SUCCESS: Exceeded 60% recovery goal!")
        else:
            print(f"⚠️  PROGRESS: Recovery at {both*100/max(1,total):.1f}%.")

    except Exception as e:
        logger.error(f"Evaluation failed: {e}")

if __name__ == "__main__":
    import sys
    batch = sys.argv[1] if len(sys.argv) > 1 else "recovery_targets.txt"
    evaluate_batch("roadmap", batch)
