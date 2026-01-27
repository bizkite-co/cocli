import math
import os
import json
from typing import List, Dict, Optional, Any
from rich.console import Console

# Optional dependency for high-quality KML generation
try:
    import simplekml # type: ignore
    SIMPLEKML_AVAILABLE = True
except ImportError:
    SIMPLEKML_AVAILABLE = False

console = Console()

# 0.08 degrees is approximately 5.5 miles at the equator.
# This results in tiles that are roughly 5.5 x 5.5 miles.
DEFAULT_GRID_STEP_DEG = 0.08

def generate_global_grid(center_lat: float, center_lon: float, radius_miles: float, step_deg: float = DEFAULT_GRID_STEP_DEG) -> List[Dict[str, Any]]:
    """
    Generates a grid of tiles covering a circular area defined by a center and radius.
    
    Args:
        center_lat: Latitude of the center point.
        center_lon: Longitude of the center point.
        radius_miles: Radius of the coverage area in miles.
        step_deg: The size of each square tile in degrees.
        
    Returns:
        A list of tile dictionaries, each containing its bounds and center.
    """
    # Rough conversion: 1 degree latitude is ~69 miles
    # 1 degree longitude varies by latitude: 69 * cos(lat)
    
    lat_step = step_deg
    lon_step = step_deg / math.cos(math.radians(center_lat))
    
    # Calculate search bounds in degrees
    lat_buffer_deg = radius_miles / 69.0
    lon_buffer_deg = radius_miles / (69.0 * math.cos(math.radians(center_lat)))
    
    min_lat = center_lat - lat_buffer_deg
    max_lat = center_lat + lat_buffer_deg
    min_lon = center_lon - lon_buffer_deg
    max_lon = center_lon + lon_buffer_deg
    
    # Align grid to steps
    start_lat = math.floor(min_lat / lat_step) * lat_step
    start_lon = math.floor(min_lon / lon_step) * lon_step
    
    grid_tiles = []
    
    current_lat = start_lat
    while current_lat <= max_lat:
        current_lon = start_lon
        while current_lon <= max_lon:
            # Check if tile center is within radius (using Haversine or simple approximation)
            tile_center_lat = current_lat + (lat_step / 2)
            tile_center_lon = current_lon + (lon_step / 2)
            
            # Simple Euclidean distance in miles (approximation)
            d_lat = (tile_center_lat - center_lat) * 69.0
            d_lon = (tile_center_lon - center_lon) * 69.0 * math.cos(math.radians(center_lat))
            dist = math.sqrt(d_lat**2 + d_lon**2)
            
            if dist <= radius_miles + (max(lat_step, lon_step) * 69.0): # Include partial tiles
                tile_id = f"{current_lat:.4f}_{current_lon:.4f}"
                grid_tiles.append({
                    "id": tile_id,
                    "south_west_lat": round(current_lat, 6),
                    "south_west_lon": round(current_lon, 6),
                    "north_east_lat": round(current_lat + lat_step, 6),
                    "north_east_lon": round(current_lon + lon_step, 6),
                    "center_lat": round(tile_center_lat, 6),
                    "center_lon": round(tile_center_lon, 6),
                    "step_deg": step_deg,
                    "est_width_miles": round(lon_step * 69.0 * math.cos(math.radians(center_lat)), 2),
                    "est_height_miles": round(lat_step * 69.0, 2)
                })
            
            current_lon += lon_step
        current_lat += lat_step
        
    return grid_tiles

def get_campaign_grid_tiles(campaign_name: str, target_locations: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Helper to load grid tiles for a campaign from its config or provided locations."""
    from cocli.core.config import load_campaign_config, get_campaign_dir
    config = load_campaign_config(campaign_name)
    campaign_dir = get_campaign_dir(campaign_name)
    
    proximity = config.get("prospecting", {}).get("proximity-miles", 10)
    
    if target_locations is None:
        target_locations = []
        prospecting_config = config.get("prospecting", {})
        target_locations_csv = prospecting_config.get("target-locations-csv")

        # 1. Try to load from CSV first
        if target_locations_csv and campaign_dir:
            import csv
            csv_path = Path(target_locations_csv)
            if not csv_path.is_absolute():
                csv_path = campaign_dir / csv_path
            
            if csv_path.exists():
                try:
                    with open(csv_path, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            name = row.get("name") or row.get("city")
                            lat = row.get("lat")
                            lon = row.get("lon")
                            if name and lat and lon and lat.strip() and lon.strip():
                                target_locations.append({
                                    "name": str(name),
                                    "lat": float(lat),
                                    "lon": float(lon)
                                })
                    if target_locations:
                        console.print(f"[dim]Loaded {len(target_locations)} target locations from {csv_path.name}[/dim]")
                except Exception as e:
                    console.print(f"[red]Error reading target locations CSV: {e}[/red]")

        # 2. Fallback to geocoding 'target-locations' list if still empty
        if not target_locations:
            locations = prospecting_config.get("target-locations", [])
            if not locations:
                # Legacy check for 'locations'
                locations = prospecting_config.get("locations", [])
            
            if locations:
                from geopy.geocoders import Nominatim # type: ignore
                geolocator = Nominatim(user_agent="cocli_planner")

                for loc in locations:
                    try:
                        if isinstance(loc, str):
                            console.print(f"[dim]Geocoding {loc}...[/dim]")
                            location = geolocator.geocode(loc)
                            if not location:
                                continue
                            lat, lon = location.latitude, location.longitude
                        else:
                            lat, lon = loc[0], loc[1]
                        
                        target_locations.append({
                            "name": str(loc),
                            "lat": lat,
                            "lon": lon
                        })
                    except Exception as e:
                        console.print(f"[red]Error geocoding {loc}: {e}[/red]")
    
    all_tiles = []
    seen_ids = set()

    for loc in target_locations:
        try:
            tiles = generate_global_grid(loc["lat"], loc["lon"], proximity)
            for t in tiles:
                if t["id"] not in seen_ids:
                    all_tiles.append(t)
                    seen_ids.add(t["id"])
        except Exception as e:
            console.print(f"[red]Error processing location {loc.get('name')}: {e}[/red]")
            
    return all_tiles

def export_to_kml(tiles: List[Dict[str, Any]], filename: str, campaign_name: str, color: Optional[str] = None) -> None:
    """
    Exports grid tiles to a KML file.
    
    Args:
        tiles: List of tile dictionaries.
        filename: Destination path for the KML file.
        campaign_name: Name of the campaign.
        color: Optional KML color (AABBGGRR).
    """
    if SIMPLEKML_AVAILABLE:
        kml = simplekml.Kml()
        kml.document.name = f"{campaign_name} - Coverage Grid"
        
        for tile in tiles:
            pol = kml.newpolygon(name=tile["id"])
            pol.outerboundaryis = [
                (tile["south_west_lon"], tile["south_west_lat"]),
                (tile["north_east_lon"], tile["south_west_lat"]),
                (tile["north_east_lon"], tile["north_east_lat"]),
                (tile["south_west_lon"], tile["north_east_lat"]),
                (tile["south_west_lon"], tile["south_west_lat"])
            ]
            
            if color:
                pol.style.polystyle.color = color
            else:
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
    else:
        # Compact Manual KML Build
        kml_color = color if color else "64ff0000" # default 40% blue
        placemarks = []
        for tile in tiles:
            coords = (
                f"{tile['south_west_lon']},{tile['south_west_lat']},0 "
                f"{tile['north_east_lon']},{tile['south_west_lat']},0 "
                f"{tile['north_east_lon']},{tile['north_east_lat']},0 "
                f"{tile['south_west_lon']},{tile['north_east_lat']},0 "
                f"{tile['south_west_lon']},{tile['south_west_lat']},0"
            )
            pm = f"<Placemark><name>{tile['id']}</name><styleUrl>#s</styleUrl><Polygon><outerBoundaryIs><LinearRing><coordinates>{coords}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>"
            placemarks.append(pm)
            
        kml_content = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<kml xmlns=\"http://www.opengis.net/kml/2.2\">
<Document>
    <name>{campaign_name} - All Targets Global Grid</name>
    <Style id=\"s\">
        <LineStyle><color>ff00ff00</color><width>1</width></LineStyle>
        <PolyStyle><color>{kml_color}</color></PolyStyle>
    </Style>
    {"" .join(placemarks)}
</Document>
</kml>"""
        with open(filename, 'w') as f:
            f.write(kml_content)
            
    console.print(f"[green]Generated KML: {filename}[/green]")

if __name__ == "__main__":
    # Example Usage: Austin, TX
    CAMPAIGN_NAME = "test/austin_test_campaign"
    CENTER_LAT = 30.2672  # Austin, TX
    CENTER_LON = -97.7431 # Austin, TX
    RADIUS_MILES = 10     # 10 miles radius
    
    # Using 0.08 degrees as the global step (~5.5 miles)
    STEP_DEG = DEFAULT_GRID_STEP_DEG 

    # Generate the grid
    grid_tiles = generate_global_grid(CENTER_LAT, CENTER_LON, RADIUS_MILES, STEP_DEG)
    console.print(f"Generated {len(grid_tiles)} global grid tiles for campaign '{CAMPAIGN_NAME}'")

    # Define output file paths in the 'exports' subdirectory
    base_dir = f"data/campaigns/{CAMPAIGN_NAME}/exports"
    output_json_file = os.path.join(base_dir, "grid_plan.json")
    output_kml_file = os.path.join(base_dir, "grid_plan.kml")

    # Ensure output directory exists
    os.makedirs(base_dir, exist_ok=True)
    
    # Save to JSON
    with open(output_json_file, "w") as f:
        json.dump(grid_tiles, f, indent=2)
    console.print(f"Saved grid plan to JSON: {output_json_file}")

    # Export to KML
    export_to_kml(grid_tiles, output_kml_file, CAMPAIGN_NAME)