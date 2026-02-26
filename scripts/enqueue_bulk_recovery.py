# POLICY: frictionless-data-policy-enforcement
import logging
import asyncio
from typing import List, Dict, Any
import duckdb

from cocli.core.paths import paths
from cocli.core.queue.factory import get_queue_manager
from cocli.models.campaigns.queues.gm_details import GmItemTask

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("bulk_enqueue")

def get_hollow_place_ids(campaign_name: str, limit: int = 10000) -> List[Dict[str, Any]]:
    """
    Uses DuckDB to find companies that have a Place ID but no rating.
    Uses positional indexing to bypass alignment issues.
    """
    prospects_path = paths.campaign(campaign_name).index("google_maps_prospects").checkpoint
    if not prospects_path.exists():
        logger.error(f"Checkpoint not found: {prospects_path}")
        return []

    logger.info(f"Scanning checkpoint: {prospects_path}")
    con = duckdb.connect(database=':memory:')
    
    try:
        # Check column 25 for rating (0-indexed)
        query = f"""
            SELECT column00, column01, column02
            FROM read_csv('{prospects_path}', delim='\x1f', header=False, auto_detect=True, 
                          all_varchar=True, ignore_errors=True, null_padding=True)
            WHERE column00 IS NOT NULL 
              AND column00 LIKE 'ChIJ%'
              AND (column25 IS NULL OR column25 = '')
            LIMIT {limit}
        """
        results = con.execute(query).fetchall()
        return [{"place_id": r[0], "slug": r[1], "name": r[2]} for r in results]
    except Exception as e:
        logger.error(f"DuckDB query failed: {e}")
        return []

async def bulk_enqueue(campaign_name: str, limit: int = 10000) -> None:
    logger.info(f"--- Bulk Enqueue for Recovery: {campaign_name} ---")
    
    # 1. Identify Targets
    targets = get_hollow_place_ids(campaign_name, limit)
    logger.info(f"Found {len(targets)} hollow targets.")
    
    if not targets:
        return

    # 2. Initialize S3 Queue
    queue_manager = get_queue_manager("details", use_cloud=True, queue_type="gm_list_item", campaign_name=campaign_name)
    
    # 3. Enqueue
    count = 0
    for target in targets:
        try:
            task = GmItemTask(
                place_id=target["place_id"],
                campaign_name=campaign_name,
                company_slug=target["slug"],
                name=target["name"],
                force_refresh=True
            )
            queue_manager.push(task)
            count += 1
            if count % 100 == 0:
                logger.info(f"Enqueued {count}...")
        except Exception as e:
            logger.error(f"Failed to enqueue {target['place_id']}: {e}")

    logger.info(f"Finished bulk enqueue. Total: {count}")

if __name__ == "__main__":
    import sys
    campaign = sys.argv[1] if len(sys.argv) > 1 else "roadmap"
    asyncio.run(bulk_enqueue(campaign))
