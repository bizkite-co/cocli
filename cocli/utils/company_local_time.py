"""Resolve a company's local timezone and format the current time there."""

from __future__ import annotations

from datetime import datetime, tzinfo
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from tzlocal import get_localzone


_ABBREV_TO_ZONE = {
    "PT": "America/Los_Angeles",
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
    "MT": "America/Denver",
    "MST": "America/Denver",
    "MDT": "America/Denver",
    "CT": "America/Chicago",
    "CST": "America/Chicago",
    "CDT": "America/Chicago",
    "ET": "America/New_York",
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "AKT": "America/Anchorage",
    "AKST": "America/Anchorage",
    "AKDT": "America/Anchorage",
    "HT": "Pacific/Honolulu",
    "HST": "Pacific/Honolulu",
    "HAST": "Pacific/Honolulu",
}

# Majority IANA zone per USPS state code. Split states pick the most
# populated zone (Texas -> Chicago, Florida -> New_York, etc.).
_STATE_TO_ZONE = {
    "AL": "America/Chicago",
    "AK": "America/Anchorage",
    "AZ": "America/Phoenix",
    "AR": "America/Chicago",
    "CA": "America/Los_Angeles",
    "CO": "America/Denver",
    "CT": "America/New_York",
    "DE": "America/New_York",
    "DC": "America/New_York",
    "FL": "America/New_York",
    "GA": "America/New_York",
    "HI": "Pacific/Honolulu",
    "ID": "America/Boise",
    "IL": "America/Chicago",
    "IN": "America/Indiana/Indianapolis",
    "IA": "America/Chicago",
    "KS": "America/Chicago",
    "KY": "America/New_York",
    "LA": "America/Chicago",
    "ME": "America/New_York",
    "MD": "America/New_York",
    "MA": "America/New_York",
    "MI": "America/Detroit",
    "MN": "America/Chicago",
    "MS": "America/Chicago",
    "MO": "America/Chicago",
    "MT": "America/Denver",
    "NE": "America/Chicago",
    "NV": "America/Los_Angeles",
    "NH": "America/New_York",
    "NJ": "America/New_York",
    "NM": "America/Denver",
    "NY": "America/New_York",
    "NC": "America/New_York",
    "ND": "America/Chicago",
    "OH": "America/New_York",
    "OK": "America/Chicago",
    "OR": "America/Los_Angeles",
    "PA": "America/New_York",
    "RI": "America/New_York",
    "SC": "America/New_York",
    "SD": "America/Chicago",
    "TN": "America/Chicago",
    "TX": "America/Chicago",
    "UT": "America/Denver",
    "VT": "America/New_York",
    "VA": "America/New_York",
    "WA": "America/Los_Angeles",
    "WV": "America/New_York",
    "WI": "America/Chicago",
    "WY": "America/Denver",
}


def resolve_company_tz(
    timezone_name: Optional[str] = None, state: Optional[str] = None
) -> tzinfo:
    """Best-effort tz for a company: explicit IANA/abbrev, then US state, then local."""
    if timezone_name:
        raw = timezone_name.strip()
        mapped = _ABBREV_TO_ZONE.get(raw.upper())
        candidate = mapped or raw
        try:
            return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            pass
    if state:
        zone = _STATE_TO_ZONE.get(state.strip().upper())
        if zone:
            try:
                return ZoneInfo(zone)
            except (ZoneInfoNotFoundError, ValueError, KeyError):
                pass
    return get_localzone()


def format_company_local_now(
    timezone_name: Optional[str] = None, state: Optional[str] = None
) -> str:
    """Current local time, e.g. 'Fri 2:34:12 PM PDT'."""
    tz = resolve_company_tz(timezone_name, state)
    now = datetime.now(tz)
    hour = now.strftime("%I").lstrip("0") or "12"
    zone = now.strftime("%Z") or (tz.key if hasattr(tz, "key") else "")
    stamp = f"{now.strftime('%a')} {hour}:{now.strftime('%M:%S %p')}"
    return f"{stamp} {zone}".strip()
