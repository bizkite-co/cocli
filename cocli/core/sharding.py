from typing import Union

def get_place_id_shard(place_id: str) -> str:
    """
    Returns a deterministic 1-character shard ID for a Google Place ID.
    Uses the 6th character (index 5) for 1-level sharding.
    """
    if not place_id or len(place_id) < 6:
        return "_"
    
    char = place_id[5]
    if char.isalnum():
        return char
    return "_"

def get_place_id_shard_from_last_character_of_place_id(place_id: str) -> str:
    """
    ALTERNATIVE STRATEGY: Returns a shard ID based on the LAST character.
    This is used for compatibility with the 'Gold Standard' migration requirements.
    """
    if not place_id:
        return "_"
    
    char = place_id[-1]
    if char.isalnum():
        return char
    return "_"

def get_geo_shard(latitude: Union[float, str]) -> str:
    """
    Returns a shard ID based on the geographic region (latitude).
    Uses the first digit of the latitude string.
    Example: 37.5 -> '3', 40.2 -> '4', -12.3 -> '-'
    """
    lat_str = str(latitude).strip()
    if not lat_str:
        return "_"
    
    return lat_str[0]

def get_grid_tile_id(latitude: float, longitude: float) -> str:
    """
    Returns a standardized 0.1-degree grid tile ID (southwest corner).
    Example: (32.99, -117.99) -> "32.9_-118.0"
    Note: Using math.floor / 10 to ensure we get the southwest corner correctly.
    """
    import math
    # tenth-of-a-degree precision
    lat_tile = math.floor(latitude * 10) / 10.0
    lon_tile = math.floor(longitude * 10) / 10.0
    return f"{lat_tile:.1f}_{lon_tile:.1f}"

# Legacy Alias
def get_shard_id(identifier: str) -> str:
    """Legacy generic sharding. Defaults to Place ID logic."""
    return get_place_id_shard(identifier)

def get_domain_shard(domain: str) -> str:
    """
    Returns a deterministic shard ID (00-ff) based on domain hash.
    Matches the DomainIndexManager 'Gold Standard' for domain-centric data.
    """
    import hashlib
    if not domain:
        return "__"
    return hashlib.sha256(domain.encode()).hexdigest()[:2]
