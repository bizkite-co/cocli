"""Build a Google Maps URL that actually searches for the place.

``query=google&query_place_id=...`` was a shortcut that now opens Maps at
the user's current location searching for the word "google". Prefer a
human query (name + street + city) plus ``query_place_id`` when we have it.
"""

from __future__ import annotations

from typing import Any, Optional
from urllib.parse import quote_plus


def google_maps_url(
    *,
    place_id: Optional[str] = None,
    name: Optional[Any] = None,
    street_address: Optional[Any] = None,
    city: Optional[Any] = None,
) -> Optional[str]:
    query = " ".join(
        str(part).strip()
        for part in (name, street_address, city)
        if part is not None and str(part).strip()
    )
    if place_id and query:
        return (
            "https://www.google.com/maps/search/?api=1"
            f"&query={quote_plus(query)}"
            f"&query_place_id={place_id}"
        )
    if place_id:
        return (
            "https://www.google.com/maps/search/?api=1"
            f"&query={quote_plus(str(place_id))}"
            f"&query_place_id={place_id}"
        )
    if query:
        return f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"
    return None
