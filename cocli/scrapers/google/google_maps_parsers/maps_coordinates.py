"""Coordinate extraction from Google Maps URLs.

Shared by both scrape paths: the list view (extract_gmb_url_coordinates_
place_id) and the detail page (parse_gmb_page, via the scrape's own witness
URL). Maps place URLs carry coordinates twice:

- camera:  @55.679577,12.5420772,17z  (the map viewport center)
- pin:     !3d55.679577!4d12.5420772  (the place marker)

The pin is the place itself; the camera is roughly "somewhere near it" at a
zoom level, so the pin wins when both are present.
"""
from __future__ import annotations

import re
from typing import NamedTuple, Optional


class GeoPoint(NamedTuple):
    latitude: float
    longitude: float


# Pin (place marker) - preferred signal.
_PIN_RE = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")
# Camera (viewport center). Suffixes like 17z may follow.
_CAMERA_RE = re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)")

# Cap on URL length: place URLs can be huge; avoid regexing on garbage wider
# than any real Maps URL pattern needs (coordinates show up well either side
# of a megabyte, but an unbounded input is still a mistake).
_MAX_URL_LEN = 4_000_000


def maps_coordinates(url: Optional[str]) -> Optional[GeoPoint]:
    """lat/lon point encoded in a Maps URL, pin first, else camera.

    Returns None when the URL is empty, oversized, or carries no
    recognizable coordinate pair. Never raises on odd input.
    """
    if not url or not isinstance(url, str) or len(url) > _MAX_URL_LEN:
        return None

    match = _PIN_RE.search(url)
    if not match:
        match = _CAMERA_RE.search(url)
    if not match:
        return None

    try:
        point = GeoPoint(latitude=float(match.group(1)), longitude=float(match.group(2)))
    except ValueError:
        return None
    return point
