from typing import Union
from .geo_types import LatScale1, LonScale1

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
    Strictly aligned to Scale 1 precision.
    """
    lat = LatScale1(latitude)
    lon = LonScale1(longitude)
    return f"{lat}_{lon}"

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
