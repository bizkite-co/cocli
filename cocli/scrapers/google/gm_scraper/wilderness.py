import logging
from typing import Dict, Optional
from ....core.scrape_index import ScrapeIndex

logger = logging.getLogger(__name__)

class WildernessManager:
    def __init__(self, overlap_threshold: float = 60.0, ttl_days: int = 30):
        self.index = ScrapeIndex()
        self.overlap_threshold = overlap_threshold
        self.ttl_days = ttl_days

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

    def mark_scraped(self, bounds: Dict[str, float], query: str, items_found: int, width_miles: float, height_miles: float, tile_id: Optional[str] = None, processed_by: Optional[str] = None) -> None:
        """Updates the index with the results."""
        # Always mark as scraped for the specific query, even if 0 items found.
        # We no longer mark "Wilderness" (global empty).
        #
        # This witness file is local-only by design: it records a timestamp +
        # item count, not the actual scraped results, so mirroring it to a
        # global (non-campaign-scoped) S3 prefix never actually let one
        # campaign skip re-scraping another's tiles - it has no IAM grant on
        # the scraper role either, so it only produced AccessDenied noise.
        # `cocli audit scrape`'s Completed/Pending Scraped Tiles metrics read
        # this file locally per-campaign, which is the only thing it's for.
        self.index.add_area(
            phrase=query,
            bounds=bounds,
            lat_miles=height_miles,
            lon_miles=width_miles,
            items_found=items_found,
            tile_id=tile_id,
            processed_by=processed_by
        )