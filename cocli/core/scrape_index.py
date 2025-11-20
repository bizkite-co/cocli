
import csv
from datetime import datetime, timedelta
from typing import List, Optional, NamedTuple
import logging

from .config import get_cocli_base_dir
from ..core.utils import slugify

logger = logging.getLogger(__name__)

class ScrapedArea(NamedTuple):
    """Represents a single entry in the scrape index."""
    phrase: str
    scrape_date: datetime
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    lat_miles: float
    lon_miles: float

class ScrapeIndex:
    """Manages the index of previously scraped geographic areas."""

    def __init__(self, campaign_name: str):
        self.index_dir = get_cocli_base_dir() / "indexes" / campaign_name
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.index_dir / "scraped_areas.csv"
        self._index: List[ScrapedArea] = []
        self._load_index()

    def _load_index(self) -> None:
        if not self.index_file.exists():
            return
        
        try:
            with self.index_file.open('r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader)  # Read header
                # Determine column indices dynamically
                try:
                    phrase_idx = header.index('phrase')
                    scrape_date_idx = header.index('scrape_date')
                    lat_min_idx = header.index('lat_min')
                    lat_max_idx = header.index('lat_max')
                    lon_min_idx = header.index('lon_min')
                    lon_max_idx = header.index('lon_max')
                    lat_miles_idx = header.index('lat_miles')
                    lon_miles_idx = header.index('lon_miles')
                except ValueError as e:
                    logger.error(f"Missing expected column in scrape_index header: {e}. Recreating index.")
                    self.index_file.unlink(missing_ok=True) # Delete old index if header is malformed
                    return

                for row in reader:
                    try:
                        self._index.append(ScrapedArea(
                            phrase=row[phrase_idx],
                            scrape_date=datetime.fromisoformat(row[scrape_date_idx]),
                            lat_min=float(row[lat_min_idx]),
                            lat_max=float(row[lat_max_idx]),
                            lon_min=float(row[lon_min_idx]),
                            lon_max=float(row[lon_max_idx]),
                            lat_miles=float(row[lat_miles_idx]),
                            lon_miles=float(row[lon_miles_idx]),
                        ))
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Skipping malformed row in scrape_index: {row} - {e}")
        except Exception as e:
            logger.error(f"Failed to load scrape index: {e}")

    def add_area(self, phrase: str, bounds: dict[str, float], lat_miles: float, lon_miles: float) -> None:
        """Adds a new scraped area to the index and saves it."""
        if not all(key in bounds for key in ['lat_min', 'lat_max', 'lon_min', 'lon_max']):
            logger.warning("Attempted to add area with incomplete bounds.")
            return

        area = ScrapedArea(
            phrase=slugify(phrase),
            scrape_date=datetime.now(),
            lat_min=bounds['lat_min'],
            lat_max=bounds['lat_max'],
            lon_min=bounds['lon_min'],
            lon_max=bounds['lon_max'],
            lat_miles=lat_miles,
            lon_miles=lon_miles,
        )
        self._index.append(area)
        
        # Save immediately
        self._save_index()

    def _save_index(self) -> None:
        """Saves the current index to the CSV file."""
        try:
            with self.index_file.open('w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['phrase', 'scrape_date', 'lat_min', 'lat_max', 'lon_min', 'lon_max', 'lat_miles', 'lon_miles'])
                for area in self._index:
                    writer.writerow([
                        area.phrase,
                        area.scrape_date.isoformat(),
                        area.lat_min,
                        area.lat_max,
                        area.lon_min,
                        area.lon_max,
                        area.lat_miles,
                        area.lon_miles,
                    ])
        except Exception as e:
            logger.error(f"Failed to save scrape index: {e}")

    def is_area_scraped(self, phrase: str, lat: float, lon: float, ttl_days: Optional[int] = None) -> Optional[ScrapedArea]:
        """
        Checks if a given coordinate for a specific phrase falls within any of the
        already scraped bounding boxes.

        Returns the matching ScrapedArea if found, otherwise None.
        """
        slugified_phrase = slugify(phrase)
        fresh_delta = timedelta(days=ttl_days) if ttl_days is not None else None

        for area in self._index:
            if area.phrase == slugified_phrase:
                # Check if the entry is stale
                if fresh_delta and (datetime.now() - area.scrape_date > fresh_delta):
                    continue

                # Check if the coordinate is within the bounding box
                if (area.lat_min <= lat <= area.lat_max) and \
                   (area.lon_min <= lon <= area.lon_max):
                    return area
        return None
