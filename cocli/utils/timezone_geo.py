"""Offline timezone derivation from a geographic point.

Uses timezonefinder (local shapefile data - no network), so a details scrape
can fill its own timezone without a per-company HTTP lookup. The Maps page
does not provide an IANA zone; this is the only offline way to get one.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

# Fully one-zone countries: falling back "point missing" from the country
# code to this zone can't pick the wrong offset. Multi-zone countries are
# deliberately absent (USA/CA/AU included) - a country code is not a zone.
ONE_ZONE_COUNTRIES: dict[str, str] = {
    "DK": "Europe/Copenhagen",
    "EE": "Europe/Tallinn",
    "IS": "Atlantic/Reykjavik",
    "LV": "Europe/Riga",
    "LT": "Europe/Vilnius",
    "LU": "Europe/Luxembourg",
    "MC": "Europe/Monaco",
    "MT": "Europe/Malta",
    "NL": "Europe/Amsterdam",
    "NO": "Europe/Oslo",
    "SM": "Europe/San_Marino",
    "VA": "Europe/Rome",
}


@lru_cache(maxsize=1)
def _finder() -> "Any":
    from timezonefinder import TimezoneFinder

    return TimezoneFinder()


def timezone_at(latitude: Optional[float], longitude: Optional[float]) -> Optional[str]:
    """IANA zone name for a point, or None. Never raises, never touches the net."""
    if latitude is None or longitude is None:
        return None
    try:
        zone = _finder().timezone_at(lat=float(latitude), lng=float(longitude))
        return str(zone) if zone else None
    except Exception:
        return None
