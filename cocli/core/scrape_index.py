
import csv
from datetime import datetime, timedelta
from typing import List, Optional, NamedTuple
from pathlib import Path
import logging

from .config import get_scraped_areas_index_dir
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
    """Manages the index of previously scraped geographic areas, stored per-phrase."""

    def __init__(self) -> None:
        self.index_dir = get_scraped_areas_index_dir()

    def _get_index_file(self, phrase: str) -> Path:
        """Returns the CSV file path for a specific phrase."""
        return self.index_dir / f"{slugify(phrase)}.csv"

    def _load_areas_for_phrase(self, phrase: str) -> List[ScrapedArea]:
        """Loads scraped areas for a specific phrase from its CSV file."""
        index_file = self._get_index_file(phrase)
        areas: List[ScrapedArea] = []
        
        if not index_file.exists():
            return areas
        
        try:
            with index_file.open('r', encoding='utf-8') as f:
                reader = csv.reader(f)
                try:
                    header = next(reader)  # Read header
                except StopIteration:
                    return areas # Empty file

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
                    logger.error(f"Missing expected column in scrape_index header for {phrase}: {e}. Recreating index.")
                    # We might want to backup instead of delete, but for now matching old behavior
                    index_file.unlink(missing_ok=True)
                    return areas

                for row in reader:
                    try:
                        areas.append(ScrapedArea(
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
                        logger.warning(f"Skipping malformed row in scrape_index for {phrase}: {row} - {e}")
        except Exception as e:
            logger.error(f"Failed to load scrape index for {phrase}: {e}")
            
        return areas

    def _save_areas_for_phrase(self, phrase: str, areas: List[ScrapedArea]) -> None:
        """Saves the list of areas to the phrase's CSV file."""
        index_file = self._get_index_file(phrase)
        try:
            with index_file.open('w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['phrase', 'scrape_date', 'lat_min', 'lat_max', 'lon_min', 'lon_max', 'lat_miles', 'lon_miles'])
                for area in areas:
                    writer.writerow([
                        area.phrase,
                        area.scrape_date.isoformat(),
                        f"{area.lat_min:.5f}",
                        f"{area.lat_max:.5f}",
                        f"{area.lon_min:.5f}",
                        f"{area.lon_max:.5f}",
                        f"{area.lat_miles:.3f}",
                        f"{area.lon_miles:.3f}",
                    ])
        except Exception as e:
            logger.error(f"Failed to save scrape index for {phrase}: {e}")

    def add_area(self, phrase: str, bounds: dict[str, float], lat_miles: float, lon_miles: float) -> None:
        """Adds a new scraped area to the index and saves it."""
        if not all(key in bounds for key in ['lat_min', 'lat_max', 'lon_min', 'lon_max']):
            logger.warning("Attempted to add area with incomplete bounds.")
            return

        # Load existing to append (naive, could optimize to append-only file mode if read/write not mixed)
        areas = self._load_areas_for_phrase(phrase)

        new_area = ScrapedArea(
            phrase=slugify(phrase),
            scrape_date=datetime.now(),
            lat_min=bounds['lat_min'],
            lat_max=bounds['lat_max'],
            lon_min=bounds['lon_min'],
            lon_max=bounds['lon_max'],
            lat_miles=lat_miles,
            lon_miles=lon_miles,
        )
        areas.append(new_area)
        
        self._save_areas_for_phrase(phrase, areas)

    def is_area_scraped(self, phrase: str, lat: float, lon: float, ttl_days: Optional[int] = None) -> Optional[ScrapedArea]:
        """
        Checks if a given coordinate for a specific phrase falls within any of the
        already scraped bounding boxes.
        """
        areas = self._load_areas_for_phrase(phrase)
        fresh_delta = timedelta(days=ttl_days) if ttl_days is not None else None

        # Check in reverse order (newest first) might be better? 
        # But CSV load order is oldest first usually.
        for area in areas:
            # Check if the entry is stale
            if fresh_delta and (datetime.now() - area.scrape_date > fresh_delta):
                continue

            # Check if the coordinate is within the bounding box
            if (area.lat_min <= lat <= area.lat_max) and \
               (area.lon_min <= lon <= area.lon_max):
                return area
        return None

    def get_all_areas_for_phrases(self, phrases: List[str]) -> List[ScrapedArea]:
        """
        Aggregates all scraped areas for a list of phrases.
        Useful for visualizing coverage for a campaign.
        """
        all_areas = []
        for phrase in phrases:
            all_areas.extend(self._load_areas_for_phrase(phrase))
        return all_areas
