import logging
from typing import Iterator, Tuple, List, Dict, Any
from .utils import calculate_new_coords

logger = logging.getLogger(__name__)

class SpiralStrategy:
    def __init__(self, start_lat: float, start_lon: float, step_miles: float):
        self.current_lat = start_lat
        self.current_lon = start_lon
        self.step_miles = step_miles
        self.bearings = [0, 90, 180, 270] # N, E, S, W
        self.direction_index = 0
        self.steps_in_direction = 1
        self.leg_count = 0
        self.steps_taken_in_leg = 0

    def __iter__(self) -> Iterator[Tuple[float, float]]:
        # Yield the starting point first
        yield self.current_lat, self.current_lon
        
        while True:
            # Move
            bearing = self.bearings[self.direction_index]
            self.current_lat, self.current_lon = calculate_new_coords(
                self.current_lat, self.current_lon, self.step_miles, bearing
            )
            
            yield self.current_lat, self.current_lon
            
            self.steps_taken_in_leg += 1
            if self.steps_taken_in_leg >= self.steps_in_direction:
                # Turn
                self.direction_index = (self.direction_index + 1) % 4
                self.steps_taken_in_leg = 0
                self.leg_count += 1
                if self.leg_count % 2 == 0:
                    self.steps_in_direction += 1

class GridStrategy:
    def __init__(self, tiles: List[Dict[str, Any]]):
        self.tiles = tiles

    def __iter__(self) -> Iterator[Tuple[float, float, str]]:
        logger.info(f"GridStrategy starting with {len(self.tiles)} tiles.")
        for tile in self.tiles:
            # Check for direct keys first (new format)
            lat = tile.get("center_lat")
            lon = tile.get("center_lon")
            
            # Fallback to nested 'center' dict if present (robustness)
            if lat is None or lon is None:
                center = tile.get("center", {})
                lat = center.get("lat")
                lon = center.get("lon")

            tile_id = tile.get("id", "")
            if lat is not None and lon is not None:
                logger.debug(f"Yielding tile {tile_id}: {lat}, {lon}")
                yield float(lat), float(lon), str(tile_id)
            else:
                logger.warning(f"Skipping invalid tile: {tile}")