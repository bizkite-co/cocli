from typing import Union
from .geo_types import LatScale1, LonScale1

def get_place_id_shard(place_id: str) -> str:
    """
    Deterministic 1-character path shard for a Google Place ID.

    Uses the 6th character (index 5) — one past the common ``ChIJ-`` / ``ChIJ``
    prefix — for high variability.

    Place IDs use a base64-like alphabet that includes ``-`` and ``_``. Those
    are distinct identity characters and must appear as path segments unchanged.
    Do **not** slugify non-alnum characters into ``_``: that collides dash-shard
    and underscore-shard place_ids and breaks addressability of existing data
    under ``pending/-/`` vs ``pending/_/``.

    Only missing or short identifiers fall back to ``_``.
    """
    if not place_id or len(place_id) < 6:
        return "_"
    return place_id[5]


def get_place_id_shard_from_last_character_of_place_id(place_id: str) -> str:
    """
    ALTERNATIVE STRATEGY: shard by the last character of the place_id.

    Prefer :func:`get_place_id_shard` for queue/index paths. This variant is
    retained for gold-standard migration tooling only. Same rule as the
    primary: raw alphabet character, no slugify of ``-``/``_``.
    """
    if not place_id:
        return "_"
    return place_id[-1]

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
