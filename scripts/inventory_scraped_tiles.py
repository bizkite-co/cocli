# POLICY: frictionless-data-policy-enforcement
import json
import logging
from datetime import datetime, UTC
from rich.progress import track

from cocli.core.paths import paths
from cocli.core.scrape_index import ScrapeIndex

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("inventory_tiles")

def inventory_scraped_tiles(campaign_name: str) -> None:
    results_dir = paths.campaign(campaign_name).queue("gm-list").completed / "results"
    scrape_index = ScrapeIndex()
    
    if not results_dir.exists():
        logger.warning(f"No results found at {results_dir}")
        return

    logger.info(f"Scanning results to populate ScrapeIndex: {results_dir}")
    
    # 1. Find all result USVs
    usv_files = list(results_dir.rglob("*.usv"))
    logger.info(f"Found {len(usv_files)} result files.")

    created = 0
    for usv_path in track(usv_files, description="Indexing..."):
        try:
            # Path: results/{shard}/{lat}/{lon}/{phrase}.usv
            rel_parts = usv_path.relative_to(results_dir).parts
            if len(rel_parts) != 4:
                continue
                
            # Force 1-decimal precision for directory structure
            lat_f = round(float(rel_parts[1]), 1)
            lon_f = round(float(rel_parts[2]), 1)
            lat_str = f"{lat_f:.1f}"
            lon_str = f"{lon_f:.1f}"
            phrase_slug = usv_path.stem
            
            # Check for receipt to get metadata
            receipt_path = usv_path.with_suffix(".json")
            scrape_date = None
            items_found = 0
            worker_id = "unknown"
            
            if receipt_path.exists():
                try:
                    with open(receipt_path, "r") as f:
                        data = json.load(f)
                        comp_at = data.get("completed_at")
                        if comp_at:
                            scrape_date = datetime.fromisoformat(comp_at.replace("Z", "+00:00"))
                        items_found = data.get("result_count", 0)
                        worker_id = data.get("worker_id", "unknown")
                except Exception:
                    pass

            if not scrape_date:
                scrape_date = datetime.fromtimestamp(usv_path.stat().st_mtime, UTC)

            # 2. Add to Index
            # tile_id format: lat_lon
            tile_id = f"{lat_str}_{lon_str}"
            bounds = {
                "lat_min": float(lat_str) - 0.05,
                "lat_max": float(lat_str) + 0.05,
                "lon_min": float(lon_str) - 0.05,
                "lon_max": float(lon_str) + 0.05
            }
            
            # This writes to indexes/scraped-tiles/
            res = scrape_index.add_area(
                phrase=phrase_slug,
                bounds=bounds,
                lat_miles=8.0,
                lon_miles=8.0,
                items_found=items_found,
                scrape_date=scrape_date,
                tile_id=tile_id,
                processed_by=worker_id
            )
            if res:
                created += 1
                
        except Exception as e:
            logger.debug(f"Failed to index {usv_path}: {e}")

    logger.info(f"Inventory complete. Created {created} witness records in ScrapeIndex.")

if __name__ == "__main__":
    import argparse
    from cocli.core.config import get_campaign
    parser = argparse.ArgumentParser(description="Populate ScrapeIndex from existing results.")
    parser.add_argument("campaign", nargs="?", default=get_campaign(), help="Campaign name")
    args = parser.parse_args()
    inventory_scraped_tiles(args.campaign)
