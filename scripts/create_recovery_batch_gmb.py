# POLICY: frictionless-data-policy-enforcement
import duckdb
import logging
from cocli.core.paths import paths
from cocli.utils.duckdb_utils import load_usv_to_duckdb

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("recovery_batch_gmb")

def create_gmb_batch(campaign_name: str, limit: int = 50) -> None:
    idx_paths = paths.campaign(campaign_name).index("google_maps_prospects")
    checkpoint_path = idx_paths.checkpoint
    datapackage_path = idx_paths.path / "datapackage.json"
    output_path = paths.campaign(campaign_name).path / "recovery" / "recovery_batch_50_gmb.txt"

    if not checkpoint_path.exists() or not datapackage_path.exists():
        logger.error("Checkpoint or Datapackage missing.")
        return

    logger.info(f"Scanning index via schema: {datapackage_path}")
    con = duckdb.connect(database=':memory:')
    
    try:
        # Load using our FDPE-compliant utility
        load_usv_to_duckdb(con, "prospects", checkpoint_path, datapackage_path)
        
        # Query for items with long GMB URLs but no rating
        # gmb_url is column 40 (0-indexed 39 usually, but load_usv uses names)
        # We also need to filter for place_id starting with ChIJ
        query = f"""
            SELECT place_id, slug, name, gmb_url
            FROM prospects
            WHERE place_id LIKE 'ChIJ%'
              AND gmb_url IS NOT NULL 
              AND length(gmb_url) > 50
              AND (average_rating IS NULL OR average_rating = 0 OR CAST(average_rating AS VARCHAR) = '')
            LIMIT {limit}
        """
        results = con.execute(query).fetchall()
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            for r in results:
                # Format: place_id|slug|name|gmb_url
                f.write(f"{r[0]}|{r[1]}|{r[2]}|{r[3]}\n")
                
        logger.info(f"Successfully created GMB recovery batch: {output_path}")
        logger.info(f"Found {len(results)} hollow prospects with high-fidelity URLs.")

    except Exception as e:
        logger.error(f"Batch creation failed: {e}")

if __name__ == "__main__":
    create_gmb_batch("roadmap")
