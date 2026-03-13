import math
from geopy.distance import geodesic # type: ignore

def calculate_new_coords(lat: float, lon: float, distance_miles: float, bearing: float) -> tuple[float, float]:
    """Calculate new lat/lon from a starting point, distance, and bearing."""
    start_point = (lat, lon)
    distance_km = distance_miles * 1.60934
    destination = geodesic(kilometers=distance_km).destination(start_point, bearing)
    return destination.latitude, destination.longitude

def calculate_zoom_level(lat: float, width_miles: float, viewport_width_px: int = 1920) -> float:
    """
    Approximates the Google Maps zoom level 'z' required to show a given width in miles
    at a specific latitude.
    
    Formula approximation:
    Earth Circumference at Lat = 24901 * cos(lat)
    Map Width (miles) = Earth Circumference at Lat / 2^z
    
    Wait, the viewport width in pixels also matters if we want 'width_miles' to fill the screen.
    Google Maps standard tile size is 256px.
    
    Resolution (miles/px) = 156543.03392 * cos(lat) / 2^z  (in meters, need to convert)
    156543 meters approx 97.27 miles.
    
    Resolution (miles/px) approx = 97.27 * cos(lat) / 2^z
    
    Desired Resolution = width_miles / viewport_width_px
    
    width_miles / viewport_width_px = 97.27 * cos(lat) / 2^z
    2^z = (97.27 * cos(lat) * viewport_width_px) / width_miles
    z = log2( (97.27 * cos(lat) * viewport_width_px) / width_miles )
    """
    if width_miles <= 0:
        return 15.0 # Default fallback
    
    # Cosine expects radians
    lat_rad = math.radians(lat)
    
    # Constant derived from Earth circumference in miles approx 24901
    # 24901 / 256 pixels = 97.27 miles/pixel at zoom 0
    
    # Let's use a slightly more conservative constant to ensure coverage
    # or just stick to the standard Web Mercator math.
    
    # z = log2( (EarthCircumference * cos(lat)) / width_miles ) 
    # This assumes the viewport width is "the map size".
    # Google Maps usually fits the view. 
    # Let's approximate: z=15 covers about 1-2 miles width.
    # z=14 covers 2-4 miles.
    # z=13 covers 4-8 miles.
    
    term = (24901 * math.cos(lat_rad)) / width_miles
    if term <= 0:
        return 15.0
        
    
    # The calculated z assumes the map is 256px wide (one tile). 
    # If our viewport is larger, we show more area at the same zoom.
    # So if viewport is 1000px, we see ~4x more width than 256px.
    # So we need to adjust z? 
    # Actually, the URL 'z' sets the resolution.
    # If we want 'width_miles' to span the *entire* viewport:
    # 2^z = (24901 * cos(lat)) / (width_miles / (viewport_width_px / 256))
    
    z_adjusted = math.log2( (24901 * math.cos(lat_rad)) / (width_miles * (256 / viewport_width_px)) )
    
    return round(z_adjusted, 2)

def get_viewport_bounds(center_lat: float, center_lon: float, map_width_miles: float, map_height_miles: float, margin: float = 0.0) -> dict[str, float]:
    """
    Calculates the bounding box of the map viewport.
    Margin is optional (0.0 to 1.0).
    """
    effective_width_miles = map_width_miles * (1 - 2 * margin)
    effective_height_miles = map_height_miles * (1 - 2 * margin)

    half_width = effective_width_miles / 2
    half_height = effective_height_miles / 2

    # Calculate extremes
    lat_max, _ = calculate_new_coords(center_lat, center_lon, half_height, 0)  # North
    lat_min, _ = calculate_new_coords(center_lat, center_lon, half_height, 180) # South

    # For longitude, calculate from the center latitude
    _, lon_max = calculate_new_coords(center_lat, center_lon, half_width, 90)  # East
    _, lon_min = calculate_new_coords(center_lat, center_lon, half_width, 270) # West

    return {
        'lat_min': lat_min,
        'lat_max': lat_max,
        'lon_min': lon_min,
        'lon_max': lon_max,
    }
