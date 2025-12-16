import json
import math
import logging
from datetime import datetime, timedelta, UTC
from typing import List, Optional, NamedTuple, Tuple, Iterator, Any
from pathlib import Path

from .config import get_scraped_areas_index_dir
from cocli.core.text_utils import slugify

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

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
    tile_id: Optional[str] = None

def _calculate_overlap_area(bounds1: dict[str, float], bounds2: dict[str, float]) -> float:
    """
    Calculates the overlapping area between two bounding boxes.
    Assumes bounds are in {'lat_min', 'lat_max', 'lon_min', 'lon_max'} format.
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

    return overlap_width_degrees * overlap_height_degrees

class ScrapeIndex:
    """
    Manages the index of previously scraped geographic areas.
    Uses a spatially partitioned file system structure:
    indexes/scraped_areas/{phrase}/{lat_grid}_{lon_grid}/{lat_min}_{lat_max}_{lon_min}_{lon_max}.json
    """

    def __init__(self) -> None:
        self.index_dir = get_scraped_areas_index_dir()

    def _get_grid_key(self, lat: float, lon: float) -> str:
        """Returns the grid key for spatial partitioning (1x1 degree) using floor."""
        return f"lat{math.floor(lat)}_lon{math.floor(lon)}"

    def _get_grid_dir(self, phrase: str, lat: float, lon: float) -> Path:
        """Returns the directory path for a specific phrase and grid cell."""
        return self.index_dir / slugify(phrase) / self._get_grid_key(lat, lon)

    def _parse_filename_bounds(self, filename: str) -> Optional[dict[str, Any]]:
        """
        Extracts bounds from filename formatted as {lat_min}_{lat_max}_{lon_min}_{lon_max}.json
        Returns None if format doesn't match.
        """
        try:
            stem = filename.replace(".json", "")
            parts = stem.split('_')
            if len(parts) >= 4:
                return {
                    'lat_min': float(parts[0]),
                    'lat_max': float(parts[1]),
                    'lon_min': float(parts[2]),
                    'lon_max': float(parts[3])
                }
        except ValueError:
            pass
        return None

    def _iter_areas_in_grid(self, phrase: str, grid_key: str) -> Iterator[dict[str, Any]]:
        """
        Fast scan: Yields bounds dicts for all files in a grid bucket based ONLY on filenames.
        Does not read file content.
        """
        phrase_dir = self.index_dir / slugify(phrase)
        grid_dir = phrase_dir / grid_key
        
        if not grid_dir.exists():
            return

        for file_path in grid_dir.iterdir():
            if file_path.suffix == '.json':
                bounds = self._parse_filename_bounds(file_path.name)
                if bounds:
                    # Attach the full path for later reading if needed
                    bounds['_file_path'] = str(file_path)
                    yield bounds

    def _load_area_from_file(self, file_path: Path) -> Optional[ScrapedArea]:
        """Reads the full ScrapedArea data from a JSON file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            scrape_date = datetime.fromisoformat(data['scrape_date'])
            if scrape_date.tzinfo is None:
                scrape_date = scrape_date.replace(tzinfo=UTC)
            
            return ScrapedArea(
                phrase=data['phrase'],
                scrape_date=scrape_date,
                lat_min=data['lat_min'],
                lat_max=data['lat_max'],
                lon_min=data['lon_min'],
                lon_max=data['lon_max'],
                lat_miles=data['lat_miles'],
                lon_miles=data['lon_miles'],
                items_found=data.get('items_found', 0),
                tile_id=data.get('tile_id')
            )
        except Exception as e:
            logger.error(f"Error loading area from {file_path}: {e}")
            return None

    def add_area(self, phrase: str, bounds: dict[str, float], lat_miles: float, lon_miles: float, items_found: int = 0, scrape_date: Optional[datetime] = None, tile_id: Optional[str] = None) -> None:
        """Adds a new scraped area to the index."""
        if not all(key in bounds for key in ['lat_min', 'lat_max', 'lon_min', 'lon_max']):
            logger.warning("Attempted to add area with incomplete bounds.")
            return

        phrase_slug = slugify(phrase)
        
        # Determine grid bucket based on bottom-left corner
        grid_dir = self._get_grid_dir(phrase_slug, bounds['lat_min'], bounds['lon_min'])
        grid_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename
        if tile_id:
            filename = f"{tile_id}.json"
        else:
            filename = f"{bounds['lat_min']:.5f}_{bounds['lat_max']:.5f}_{bounds['lon_min']:.5f}_{bounds['lon_max']:.5f}.json"
        
        file_path = grid_dir / filename

        data = {
            "phrase": phrase_slug,
            "scrape_date": (scrape_date or datetime.now(UTC)).isoformat(),
            "lat_min": bounds['lat_min'],
            "lat_max": bounds['lat_max'],
            "lon_min": bounds['lon_min'],
            "lon_max": bounds['lon_max'],
            "lat_miles": lat_miles,
            "lon_miles": lon_miles,
            "items_found": items_found
        }
        
        if tile_id:
            data["tile_id"] = tile_id

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f)
            logger.debug(f"Saved scraped area index: {file_path.name}")
        except Exception as e:
            logger.error(f"Failed to save scrape index {file_path}: {e}")

    def is_area_scraped(self, phrase: str, bounds: dict[str, float], ttl_days: Optional[int] = None, overlap_threshold_percent: float = 0.0) -> Optional[Tuple[ScrapedArea, float]]:
        """
        Checks if a given bounding box overlaps with existing scraped areas.
        """
        phrase_slug = slugify(phrase)
        
        # Determine relevant grid buckets.
        center_lat = (bounds['lat_min'] + bounds['lat_max']) / 2
        center_lon = (bounds['lon_min'] + bounds['lon_max']) / 2
        
        center_lat_floor = math.floor(center_lat)
        center_lon_floor = math.floor(center_lon)
        
        checked_grids = set()
        
        # Check 3x3 grid around center
        for dlat in [-1, 0, 1]:
            for dlon in [-1, 0, 1]:
                lat_key = center_lat_floor + dlat
                lon_key = center_lon_floor + dlon
                grid_key = f"lat{lat_key}_lon{lon_key}"
                
                if grid_key in checked_grids:
                    continue
                checked_grids.add(grid_key)
                
                # Scan this grid bucket
                for area_bounds in self._iter_areas_in_grid(phrase_slug, grid_key):
                    # Quick overlap check using bounds from filename
                    
                    # Ensure float typing for overlap calculation
                    calc_bounds = {k: float(v) for k, v in area_bounds.items() if k in ['lat_min', 'lat_max', 'lon_min', 'lon_max']}
                    overlap_area = _calculate_overlap_area(bounds, calc_bounds)
                    
                    current_area_size = (bounds['lon_max'] - bounds['lon_min']) * (bounds['lat_max'] - bounds['lat_min'])
                    if current_area_size <= 0:
                        continue
                        
                    percent = (overlap_area / current_area_size) * 100
                    
                    if percent >= overlap_threshold_percent:
                        # Potential match! Now we need to read the file to check date/TTL
                        file_path_str = area_bounds.get('_file_path')
                        if not file_path_str:
                             continue
                        full_area = self._load_area_from_file(Path(str(file_path_str)))
                        if not full_area:
                            continue
                            
                        if ttl_days is not None:
                            age = datetime.now(UTC) - full_area.scrape_date
                            if age > timedelta(days=ttl_days):
                                continue # Stale
                        
                        logger.debug(f"Overlap found ({percent:.1f}%) with {full_area.lat_min},{full_area.lon_min}")
                        return full_area, percent

        return None

    def add_wilderness_area(self, bounds: dict[str, float], lat_miles: float, lon_miles: float, items_found: int) -> None:
        """Adds a new wilderness area to the index."""
        self.add_area("wilderness", bounds, lat_miles, lon_miles, items_found)

    def is_wilderness_area(self, bounds: dict[str, float], overlap_threshold_percent: float = 0.0) -> Optional[Tuple[ScrapedArea, float]]:
        """Checks if a given bounding box overlaps with wilderness areas."""
        return self.is_area_scraped("wilderness", bounds, overlap_threshold_percent=overlap_threshold_percent)

    def get_wilderness_areas(self) -> List[ScrapedArea]:
        """Loads all wilderness areas."""
        return self.get_all_areas_for_phrases(["wilderness"])

    def get_all_areas_for_phrases(self, phrases: List[str]) -> List[ScrapedArea]:
        """
        Recursively loads ALL areas for the given phrases.
        Usage: KML generation (infrequent).
        """
        all_areas: List[ScrapedArea] = []
        for phrase in phrases:
            phrase_slug = slugify(phrase)
            phrase_dir = self.index_dir / phrase_slug
            
            if not phrase_dir.exists():
                continue
                
            for grid_dir in phrase_dir.iterdir():
                if grid_dir.is_dir():
                    for file_path in grid_dir.glob("*.json"):
                         area = self._load_area_from_file(file_path)
                         if area:
                             all_areas.append(area)
        return all_areas

    def get_all_scraped_areas(self) -> List[ScrapedArea]:
        """Loads ALL scraped areas (all phrases). Expensive."""
        all_areas: List[ScrapedArea] = []
        if not self.index_dir.exists():
            return all_areas
            
        for phrase_dir in self.index_dir.iterdir():
            if phrase_dir.is_dir():
                phrase = phrase_dir.name
                if phrase == "wilderness":
                     continue
                
                # Load all grids
                for grid_dir in phrase_dir.iterdir():
                    if grid_dir.is_dir():
                         for file_path in grid_dir.glob("*.json"):
                             area = self._load_area_from_file(file_path)
                             if area:
                                 all_areas.append(area)
        return all_areas