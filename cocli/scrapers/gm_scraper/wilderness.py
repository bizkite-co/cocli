import logging
from typing import Dict, Optional, Any
from ...core.scrape_index import ScrapeIndex
from ...core.config import get_scraped_areas_index_dir

logger = logging.getLogger(__name__)

class WildernessManager:
    def __init__(self, overlap_threshold: float = 60.0, ttl_days: int = 30, s3_client: Any = None, s3_bucket: Optional[str] = None):
        self.index = ScrapeIndex()
        self.overlap_threshold = overlap_threshold
        self.ttl_days = ttl_days
        self.s3_client = s3_client
        self.s3_bucket = s3_bucket
        self.base_dir = get_scraped_areas_index_dir()

    def should_scrape(self, bounds: Dict[str, float], query: str) -> bool:
        """
        Determines if an area should be scraped for a specific query.
        Returns False if:
        1. It overlaps significantly with a known Wilderness area (empty for ANY query).
        2. It overlaps significantly with a previously scraped area for THIS query.
        """
        # 1. Check Wilderness (Global) - DISABLED
        # is_wilderness = self.index.is_wilderness_area(bounds, self.overlap_threshold)
        # if is_wilderness:
        #     return False
            
        # 2. Check Scraped (Query Specific)
        is_scraped = self.index.is_area_scraped(query, bounds, self.ttl_days, self.overlap_threshold)
        if is_scraped:
            return False
            
        return True

    def mark_scraped(self, bounds: Dict[str, float], query: str, items_found: int, width_miles: float, height_miles: float, tile_id: Optional[str] = None) -> None:
        """Updates the index with the results."""
        # Always mark as scraped for the specific query, even if 0 items found.
        # We no longer mark "Wilderness" (global empty).
        file_path = self.index.add_area(
            phrase=query,
            bounds=bounds,
            lat_miles=height_miles,
            lon_miles=width_miles,
            items_found=items_found,
            tile_id=tile_id
        )

        if file_path and self.s3_client and self.s3_bucket:
            try:
                # 1. Upload legacy JSON
                # Calculate S3 Key: indexes/scraped_areas/{phrase}/{grid}/{file}
                relative_path = file_path.relative_to(self.base_dir)
                s3_key = f"indexes/scraped_areas/{relative_path}"
                self.s3_client.upload_file(str(file_path), self.s3_bucket, s3_key)
                logger.info(f"Uploaded scraped area to s3://{self.s3_bucket}/{s3_key}")

                # 2. Upload Witness CSV/USV (Phase 10)
                if tile_id:
                    from cocli.core.text_utils import slugify
                    parts = tile_id.split("_")
                    lat_str, lon_str = parts[0], parts[1]
                    phrase_slug = slugify(query)
                    
                    # Try both USV and CSV
                    for ext in [".usv", ".csv"]:
                        witness_rel_path = f"scraped-tiles/{lat_str}/{lon_str}/{phrase_slug}{ext}"
                        witness_local_path = self.base_dir.parent / witness_rel_path
                        
                        if witness_local_path.exists():
                            witness_s3_key = f"indexes/{witness_rel_path}"
                            self.s3_client.upload_file(str(witness_local_path), self.s3_bucket, witness_s3_key)
                            logger.info(f"Uploaded witness file to s3://{self.s3_bucket}/{witness_s3_key}")
                            break
            except Exception as e:
                logger.error(f"Failed to upload scraped area to S3: {e}")