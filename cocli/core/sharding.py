from typing import Union

def get_place_id_shard(place_id: str) -> str:
    """
    Returns a deterministic 1-character shard ID for a Google Place ID.
    Uses the last character for 1-level sharding.
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

# Legacy Alias
def get_shard_id(identifier: str) -> str:
    """Legacy generic sharding. Defaults to Place ID logic."""
    return get_place_id_shard(identifier)
