
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
    items_found: int

def _calculate_overlap_area(bounds1: dict[str, float], bounds2: dict[str, float]) -> float:
    """
    Calculates the overlapping area between two bounding boxes.
    Assumes bounds are in {'lat_min', 'lat_max', 'lon_min', 'lon_max'} format.
    Returns the area in 'square miles' based on lat_miles and lon_miles in ScrapedArea,
    but here we'll use a simpler lat/lon intersection for relative overlap.
    """
    # Calculate the intersection rectangle coordinates
    overlap_lon_min = max(bounds1['lon_min'], bounds2['lon_min'])
    overlap_lat_min = max(bounds1['lat_min'], bounds2['lat_min'])
    overlap_lon_max = min(bounds1['lon_max'], bounds2['lon_max'])
    overlap_lat_max = min(bounds1['lat_max'], bounds2['lat_max'])

    # If no overlap, return 0
    if overlap_lon_max < overlap_lon_min or overlap_lat_max < overlap_lat_min:
        return 0.0

    # Approximate overlap width and height in degrees
    overlap_width_degrees = overlap_lon_max - overlap_lon_min
    overlap_height_degrees = overlap_lat_max - overlap_lat_min

    # For a simple relative overlap check, we can use degrees directly.
    # If absolute area in square miles is needed, a more complex geodesic calculation is required.
    # For now, using product of degrees as a proxy for area for relative comparison.
    return overlap_width_degrees * overlap_height_degrees

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
                    items_found_idx = header.index('items_found') # New column
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
                            items_found=int(row[items_found_idx]), # New column
                        ))
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Skipping malformed row in scrape_index for {phrase}: {row} - {e}. Attempting to re-read with default items_found=0 for old format.")
                        # Attempt to parse old format without items_found for backward compatibility
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
                                items_found=0, # Default to 0 for old entries
                            ))
                        except (ValueError, IndexError) as e_fallback:
                            logger.error(f"Still failed to parse row after fallback for {phrase}: {row} - {e_fallback}")
        except Exception as e:
            logger.error(f"Failed to load scrape index for {phrase}: {e}")
            
        return areas

    def _save_areas_for_phrase(self, phrase: str, areas: List[ScrapedArea]) -> None:
        """Saves the list of areas to the phrase's CSV file."""
        index_file = self._get_index_file(phrase)
        try:
            with index_file.open('w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['phrase', 'scrape_date', 'lat_min', 'lat_max', 'lon_min', 'lon_max', 'lat_miles', 'lon_miles', 'items_found'])
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
                        area.items_found,
                    ])
        except Exception as e:
            logger.error(f"Failed to save scrape index for {phrase}: {e}")

    def add_area(self, phrase: str, bounds: dict[str, float], lat_miles: float, lon_miles: float, items_found: int = 0) -> None:
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
            items_found=items_found,
        )
        areas.append(new_area)
        
        self._save_areas_for_phrase(phrase, areas)

    def is_area_scraped(self, phrase: str, bounds: dict[str, float], ttl_days: Optional[int] = None, overlap_threshold_percent: float = 0.0) -> Optional[ScrapedArea]:
        """
        Checks if a given bounding box for a specific phrase significantly overlaps with any of the
        already scraped bounding boxes.
        """
        areas = self._load_areas_for_phrase(phrase)
        fresh_delta = timedelta(days=ttl_days) if ttl_days is not None else None

        # Calculate area of the current bounds in degrees for relative comparison
        current_bounds_width = bounds['lon_max'] - bounds['lon_min']
        current_bounds_height = bounds['lat_max'] - bounds['lat_min']
        area_of_current_bounds = current_bounds_width * current_bounds_height
        
        if area_of_current_bounds <= 0: # Avoid division by zero for point or line bounds
            return None

        for area in areas:
            # Check if the entry is stale
            if fresh_delta and (datetime.now() - area.scrape_date > fresh_delta):
                continue
            
            # Calculate overlap area
            overlap_area = _calculate_overlap_area(bounds, {
                'lat_min': area.lat_min, 'lat_max': area.lat_max,
                'lon_min': area.lon_min, 'lon_max': area.lon_max
            })
            
            overlap_percentage = (overlap_area / area_of_current_bounds) * 100

            if overlap_percentage >= overlap_threshold_percent:
                return area
        return None

    def _get_wilderness_index_file(self) -> Path:
        """Returns the CSV file path for wilderness areas."""
        return self.index_dir / "wilderness_areas.csv"

    def _load_wilderness_areas(self) -> List[ScrapedArea]:
        """Loads wilderness areas from its CSV file."""
        index_file = self._get_wilderness_index_file()
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

                try:
                    phrase_idx = header.index('phrase') # Will be 'wilderness'
                    scrape_date_idx = header.index('scrape_date')
                    lat_min_idx = header.index('lat_min')
                    lat_max_idx = header.index('lat_max')
                    lon_min_idx = header.index('lon_min')
                    lon_max_idx = header.index('lon_max')
                    lat_miles_idx = header.index('lat_miles')
                    lon_miles_idx = header.index('lon_miles')
                    items_found_idx = header.index('items_found')
                except ValueError as e:
                    logger.error(f"Missing expected column in wilderness_areas header: {e}. Recreating index.")
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
                            items_found=int(row[items_found_idx]),
                        ))
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Skipping malformed row in wilderness_areas: {row} - {e}")
        except Exception as e:
            logger.error(f"Failed to load wilderness_areas index: {e}")
            
        return areas

    def _save_wilderness_areas(self, areas: List[ScrapedArea]) -> None:
        """Saves the list of wilderness areas to its CSV file."""
        index_file = self._get_wilderness_index_file()
        try:
            with index_file.open('w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['phrase', 'scrape_date', 'lat_min', 'lat_max', 'lon_min', 'lon_max', 'lat_miles', 'lon_miles', 'items_found'])
                for area in areas:
                    writer.writerow([
                        area.phrase, # Will be 'wilderness'
                        area.scrape_date.isoformat(),
                        f"{area.lat_min:.5f}",
                        f"{area.lat_max:.5f}",
                        f"{area.lon_min:.5f}",
                        f"{area.lon_max:.5f}",
                        f"{area.lat_miles:.3f}",
                        f"{area.lon_miles:.3f}",
                        area.items_found,
                    ])
        except Exception as e:
            logger.error(f"Failed to save wilderness_areas index: {e}")

    def add_wilderness_area(self, bounds: dict[str, float], lat_miles: float, lon_miles: float, items_found: int) -> None:
        """Adds a new wilderness area to the index and saves it."""
        if not all(key in bounds for key in ['lat_min', 'lat_max', 'lon_min', 'lon_max']):
            logger.warning("Attempted to add wilderness area with incomplete bounds.")
            return

        areas = self._load_wilderness_areas()

        new_area = ScrapedArea(
            phrase="wilderness", # Generic phrase for wilderness areas
            scrape_date=datetime.now(),
            lat_min=bounds['lat_min'],
            lat_max=bounds['lat_max'],
            lon_min=bounds['lon_min'],
            lon_max=bounds['lon_max'],
            lat_miles=lat_miles,
            lon_miles=lon_miles,
            items_found=items_found,
        )
        areas.append(new_area)
        
        self._save_wilderness_areas(areas)

    def is_wilderness_area(self, bounds: dict[str, float], overlap_threshold_percent: float = 0.0) -> Optional[ScrapedArea]:
        """
        Checks if a given bounding box falls within any of the known wilderness areas.
        """
        areas = self._load_wilderness_areas()
        
        # Calculate area of the current bounds in degrees for relative comparison
        current_bounds_width = bounds['lon_max'] - bounds['lon_min']
        current_bounds_height = bounds['lat_max'] - bounds['lat_min']
        area_of_current_bounds = current_bounds_width * current_bounds_height

        if area_of_current_bounds <= 0:
            return None

        for area in areas:
            # Calculate overlap area
            overlap_area = _calculate_overlap_area(bounds, {
                'lat_min': area.lat_min, 'lat_max': area.lat_max,
                'lon_min': area.lon_min, 'lon_max': area.lon_max
            })
            
            overlap_percentage = (overlap_area / area_of_current_bounds) * 100

            if overlap_percentage >= overlap_threshold_percent:
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
