from typing import Dict
from ...core.scrape_index import ScrapeIndex

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
        # 1. Check Wilderness (Global)
        is_wilderness = self.index.is_wilderness_area(bounds, self.overlap_threshold)
        if is_wilderness:
            return False
            
        # 2. Check Scraped (Query Specific)
        is_scraped = self.index.is_area_scraped(query, bounds, self.ttl_days, self.overlap_threshold)
        if is_scraped:
            return False
            
        return True

    def mark_scraped(self, bounds: Dict[str, float], query: str, items_found: int, width_miles: float, height_miles: float) -> None:
        """Updates the index with the results."""
        if items_found > 0:
            self.index.add_area(
                phrase=query,
                bounds=bounds,
                lat_miles=height_miles,
                lon_miles=width_miles,
                items_found=items_found
            )
        else:
            # If 0 items found, it's wilderness (applies to ALL queries)
            self.index.add_wilderness_area(
                bounds=bounds,
                lat_miles=height_miles,
                lon_miles=width_miles,
                items_found=0
            )
