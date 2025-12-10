import math
import logging
from typing import List, Tuple
from ..models.target_location import TargetLocation
from ..core.scrape_index import ScrapedArea

logger = logging.getLogger(__name__)

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates Haversine distance in miles between two points."""
    R = 3958.8  # Radius of Earth in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def get_min_max_distance(lat: float, lon: float, area: ScrapedArea) -> Tuple[float, float]:
    """
    Returns the minimum and maximum distance from a point to a ScrapedArea rectangle (miles).
    """
    # Clamp point to rectangle for min distance
    clamped_lat = max(area.lat_min, min(lat, area.lat_max))
    clamped_lon = max(area.lon_min, min(lon, area.lon_max))
    
    min_dist = haversine(lat, lon, clamped_lat, clamped_lon)
    
    # Max distance is one of the 4 corners
    corners = [
        (area.lat_min, area.lon_min),
        (area.lat_min, area.lon_max),
        (area.lat_max, area.lon_min),
        (area.lat_max, area.lon_max)
    ]
    max_dist = max(haversine(lat, lon, c_lat, c_lon) for c_lat, c_lon in corners)
    
    return min_dist, max_dist

def calculate_saturation_score(target: TargetLocation, areas: List[ScrapedArea], max_proximity: float = 20.0) -> float:
    """
    Calculates the saturation score for a target location based on scraped areas.
    Score increases with more scraped areas within max_proximity.
    Weighting logic: (d_max - d_min) / (1 + d_min)
    """
    total_score = 0.0
    
    for area in areas:
        min_dist, max_dist = get_min_max_distance(target.lat, target.lon, area)
        
        if min_dist <= max_proximity:
            # Avoid division by zero if min_dist is somehow negative (shouldn't be)
            denom = 1.0 + max(0.0, min_dist)
            weight = (max_dist - min_dist) / denom
            total_score += weight
            
    return total_score
