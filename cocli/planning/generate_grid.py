import math
from typing import List, Dict, Optional, Any
import simplekml # type: ignore
from datetime import datetime
import os
import json

# Configuration for Global Grid
# We use degrees as the fundamental unit to ensure global alignment (Snap-to-Grid).
# 0.1 degrees is the standard "one decimal place" grid.
# At 30 deg lat: ~6.9 miles (lat) x 6.0 miles (lon).
# We will adjust browser viewport/zoom to match this grid size.
DEFAULT_GRID_STEP_DEG = 0.1

# Approximate miles per degree for reporting/viz only (at equator/general)
APPROX_MILES_PER_DEG_LAT = 69.0

def generate_global_grid(
    center_lat: float,
    center_lon: float,
    radius_miles: float,
    step_deg: float = DEFAULT_GRID_STEP_DEG
) -> List[Dict[str, Any]]:
    """
    Generates a grid of tiles aligned to a global Lat/Lon grid (0.1 degree steps).
    This ensures that tiles are consistent across different campaigns/cities.
    
    The grid covers the requested radius completely (no truncation).
    """
    tiles: List[Dict[str, Any]] = []

    # Convert radius to rough degrees to find bounding box
    radius_deg = radius_miles / APPROX_MILES_PER_DEG_LAT
    cos_factor = math.cos(math.radians(center_lat))
    radius_deg_lon = radius_miles / (APPROX_MILES_PER_DEG_LAT * cos_factor)
    
    raw_min_lat = center_lat - radius_deg
    raw_max_lat = center_lat + radius_deg
    raw_min_lon = center_lon - radius_deg_lon
    raw_max_lon = center_lon + radius_deg_lon

    # SNAP TO GRID (0.1 degree alignment)
    # We use round(x, 1) logic, but floor/ceil to ensure coverage
    
    def snap_floor(val: float, step: float) -> float:
        return math.floor(val / step) * step

    def snap_ceil(val: float, step: float) -> float:
        return math.ceil(val / step) * step

    grid_min_lat = snap_floor(raw_min_lat, step_deg)
    grid_max_lat = snap_ceil(raw_max_lat, step_deg)
    grid_min_lon = snap_floor(raw_min_lon, step_deg)
    grid_max_lon = snap_ceil(raw_max_lon, step_deg)

    # Generate Tiles
    current_lat = grid_min_lat
    # Iterate with a small epsilon to handle float comparisons
    epsilon = step_deg / 1000.0
    
    while current_lat < grid_max_lat - epsilon:
        current_lon = grid_min_lon
        while current_lon < grid_max_lon - epsilon:
            
            sw_lat = current_lat
            sw_lon = current_lon
            ne_lat = current_lat + step_deg
            ne_lon = current_lon + step_deg
            
            # Create a unique, consistent ID based on the South-West corner
            # e.g., "30.2_-97.7"
            # We use .1f formatting to ensure consistent strings
            tile_id = f"{sw_lat:.1f}_{sw_lon:.1f}"
            
            center_lat_calc = (sw_lat + ne_lat) / 2
            center_lon_calc = (sw_lon + ne_lon) / 2
            
            # Approximate size in miles for this specific tile (for reference)
            height_miles = step_deg * APPROX_MILES_PER_DEG_LAT
            width_miles = step_deg * APPROX_MILES_PER_DEG_LAT * math.cos(math.radians(center_lat_calc))

            tiles.append({
                "id": tile_id,
                "south_west_lat": round(sw_lat, 5),
                "south_west_lon": round(sw_lon, 5),
                "north_east_lat": round(ne_lat, 5),
                "north_east_lon": round(ne_lon, 5),
                "center_lat": round(center_lat_calc, 5),
                "center_lon": round(center_lon_calc, 5),
                "status": "pending",
                "step_deg": step_deg,
                "est_width_miles": round(width_miles, 2),
                "est_height_miles": round(height_miles, 2),
                "generated_at": datetime.utcnow().isoformat()
            })
            
            current_lon += step_deg
        current_lat += step_deg

    return tiles

def export_to_kml(tiles: List[Dict[str, Any]], filename: str, campaign_name: str, color: Optional[str] = None) -> None:
    """
    Exports the generated grid tiles to a KML file for visualization.
    """
    kml = simplekml.Kml()
    document = kml.newdocument(name=f"{campaign_name} Global Grid")

    for tile in tiles:
        pol = document.newpolygon(name=tile["id"])
        pol.outerboundaryis = [
            (tile["south_west_lon"], tile["south_west_lat"]),
            (tile["north_east_lon"], tile["south_west_lat"]),
            (tile["north_east_lon"], tile["north_east_lat"]),
            (tile["south_west_lon"], tile["north_east_lat"]),
            (tile["south_west_lon"], tile["south_west_lat"])
        ]
        
        if color:
            # color is expected in KML AABBGGRR hex format (e.g. "08ffffff")
            pol.style.polystyle.color = color
        else:
            # Transparent blue (default)
            pol.style.polystyle.color = simplekml.Color.changealphaint(100, simplekml.Color.blue)
            
        pol.style.linestyle.width = 2
        
        desc = (
            f"ID: {tile['id']}\n"
            f"Grid Step: {tile['step_deg']} deg\n"
            f"Approx Size: {tile['est_width_miles']}mi (W) x {tile['est_height_miles']}mi (H)\n"
            f"Center: {tile['center_lat']}, {tile['center_lon']}"
        )
        pol.description = desc
    
    kml.save(filename)
    print(f"Generated KML: {filename}")

if __name__ == "__main__":
    # Example Usage: Austin, TX
    CAMPAIGN_NAME = "austin_test_campaign"
    CENTER_LAT = 30.2672  # Austin, TX
    CENTER_LON = -97.7431 # Austin, TX
    RADIUS_MILES = 10     # 10 miles radius
    
    # Using 0.08 degrees as the global step (~5.5 miles)
    STEP_DEG = DEFAULT_GRID_STEP_DEG 

    # Generate the grid
    grid_tiles = generate_global_grid(CENTER_LAT, CENTER_LON, RADIUS_MILES, STEP_DEG)
    print(f"Generated {len(grid_tiles)} global grid tiles for campaign '{CAMPAIGN_NAME}'")

    # Define output file paths in the 'exports' subdirectory
    base_dir = f"cocli_data/campaigns/{CAMPAIGN_NAME}/exports"
    output_json_file = os.path.join(base_dir, "grid_plan.json")
    output_kml_file = os.path.join(base_dir, "grid_plan.kml")

    # Ensure output directory exists
    os.makedirs(base_dir, exist_ok=True)
    
    # Save to JSON
    with open(output_json_file, "w") as f:
        json.dump(grid_tiles, f, indent=2)
    print(f"Saved grid plan to JSON: {output_json_file}")

    # Export to KML
    export_to_kml(grid_tiles, output_kml_file, CAMPAIGN_NAME)